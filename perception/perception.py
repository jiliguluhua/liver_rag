import os
import sys
import torch
import numpy as np
import json
import pydicom
import matplotlib.pyplot as plt
from PIL import Image
import io
from monai.networks.nets import SwinUNETR
from monai.inferers import sliding_window_inference
from monai.transforms import Compose, LoadImaged, Spacingd, ScaleIntensityRanged, EnsureTyped, EnsureChannelFirstd

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import core.config as config

class MedicalPerception:
    def __init__(self, model_path, meta_path):
        # 1. 设备与标签初始化
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.label_map = self._load_metadata(meta_path)
        self.liver_idx = self.label_map.get("liver", 1) 
        self.tumor_idx = self.label_map.get("tumor", 2) 

        # 2. 模型初始化
        self.model = SwinUNETR(
            in_channels=1,
            out_channels=14, 
            feature_size=48
        ).to(self.device) 
        
        # 3. 加载权重
        if os.path.exists(model_path):
            checkpoint = torch.load(model_path, map_location=self.device)
            self.model.load_state_dict(checkpoint.get("state_dict", checkpoint))
            self.model.eval()
            print(f"感知模型加载成功: {model_path}")
        else:
            print(f"警告：未找到模型权重文件 {model_path}")

    def _load_metadata(self, meta_path):
        label_mapping = {}
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            raw_labels = meta.get("labels", {})
            for idx, name in raw_labels.items():
                name_lower = name.lower()
                label_mapping[name_lower] = int(idx)
            print(f"自动解析标签成功: {label_mapping}")
        else:
            print("未找到 metadata，使用默认索引 (Liver:1, Tumor:2)")
            label_mapping = {"liver": 1, "tumor": 2}
        return label_mapping

    def get_tumor_volume(self, dicom_dir):
        """
        核心业务逻辑：输入序列文件夹，输出体积(mL)及预览图(PIL Image)
        """
        # --- 第一步：推理准备 ---
        transforms = Compose([
            LoadImaged(keys=["image"]),
            EnsureChannelFirstd(keys=["image"]),
            Spacingd(keys=["image"], pixdim=(1.5, 1.5, 2.0), mode="bilinear"),
            ScaleIntensityRanged(keys=["image"], a_min=-21, a_max=189, b_min=0, b_max=1, clip=True),
            EnsureTyped(keys=["image"])
        ])
        
        # 加载数据进行推理
        data = transforms({"image": dicom_dir})
        inputs = data["image"].unsqueeze(0).to(self.device)

        # --- 第二步：模型推理 ---
        with torch.no_grad():
            outputs = sliding_window_inference(inputs, (96, 96, 96), 4, self.model)
            mask = torch.argmax(outputs, dim=1).cpu().numpy()[0]
            tumor_mask = (mask == self.tumor_idx)
            
        # 物理体积换算：1.5 * 1.5 * 2.0 = 4.5 mm³
        voxel_vol = 1.5 * 1.5 * 2.0
        tumor_pixels = np.sum(tumor_mask)
        volume_ml = (tumor_pixels * voxel_vol) / 1000.0

        # --- 第三步：生成预览图 ---
        preview_img = None
        try:
            # 1. 寻找肿瘤面积最大的切片索引
            slice_sums = np.sum(tumor_mask, axis=(1, 2))
            max_slice_idx = np.argmax(slice_sums)
            
            # 如果没扫到肿瘤，改找肝脏最大的切片
            if slice_sums[max_slice_idx] == 0:
                liver_mask = (mask == self.liver_idx)
                max_slice_idx = np.argmax(np.sum(liver_mask, axis=(1, 2)))

            # 2. 读取原始图像用于底图展示 (选取对应切片)
            # 注意：由于做了 Spacing 重采样，此处直接使用 inputs 数据展示最为准确
            raw_img = inputs[0, 0, :, :, max_slice_idx].cpu().numpy()
            mask_2d = mask[:, :, max_slice_idx]

            # 3. 绘图
            plt.figure(figsize=(8, 8))
            plt.imshow(raw_img.T, cmap='gray', origin='lower') # 转置以符合常规显示
            
            # 叠加肿瘤 Mask (红色)
            tumor_2d = (mask_2d == self.tumor_idx).T
            plt.imshow(np.ma.masked_where(tumor_2d == 0, tumor_2d), 
                       cmap='Reds', alpha=0.6, origin='lower')
            
            # 叠加肝脏 Mask (黄色/绿色)
            liver_2d = (mask_2d == self.liver_idx).T
            plt.imshow(np.ma.masked_where(liver_2d == 0, liver_2d), 
                       cmap='spring', alpha=0.3, origin='lower')

            plt.axis('off')
            plt.title(f"ROI Preview - Slice {max_slice_idx}")

            # 4. 转为 PIL 格式
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
            plt.close()
            buf.seek(0)
            preview_img = Image.open(buf)
            
        except Exception as e:
            print(f"预览图生成失败: {e}")

        return {
            "volume": volume_ml,
            "preview_img": preview_img
        }

if __name__ == "__main__":
    # 测试代码
    model_path = config.PERCEPTION_MODEL_PATH
    meta_path = config.PERCEPTION_META_PATH
    dicom_path = r"E:\postgraduate\医疗数据\CT70557-肝癌-CT增强\art"
    
    perception = MedicalPerception(model_path, meta_path)
    res = perception.get_tumor_volume(dicom_path)
    print(f"预测的肿瘤体积: {res['volume']:.2f} mL")
    if res['preview_img']:
        res['preview_img'].show()