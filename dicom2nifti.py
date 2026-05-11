import SimpleITK as sitk
import os

def dicom_to_nnunet(dicom_dir, output_folder, patient_id):
    reader = sitk.ImageSeriesReader()
    
    series_ids = reader.GetGDCMSeriesIDs(dicom_dir)
    series_file_names = reader.GetGDCMSeriesFileNames(dicom_dir, series_ids[0])
    
    reader.SetFileNames(series_file_names)
    image = reader.Execute()
    
    # 🔥 关键：统一方向（非常重要）
    image = sitk.DICOMOrient(image, 'RAS')
    
    print("Size:", image.GetSize())
    print("Spacing:", image.GetSpacing())
    
    os.makedirs(output_folder, exist_ok=True)
    output_path = os.path.join(output_folder, f"{patient_id}_0000.nii.gz")
    
    sitk.WriteImage(image, output_path)
    
    return output_path