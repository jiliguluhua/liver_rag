import re

class MedicalTextCleaner:
    def __init__(self):
        # 匹配参考文献的正则表达式：如 [1], [12-15], (2024), J Clin Oncol. 等
        self.ref_patterns = [
            r'\[\d+[\d\-\s,]*\]',        # 匹配 [1] 或 [1-3]
            r'doi:.*',                   # 匹配 DOI 链接
            r'http[s]?://.*',            # 匹配 URL
            r'\d{4},\s\d+.*:\d+-\d+\.',  # 匹配典型的期刊年份卷号
        ]

    def is_noise(self, text):
        """判断一个切片是否是噪音"""
        # 1. 长度过滤：太短的内容通常只有页码或标题
        if len(text) < 40:
            return True
        
        # 2. 关键词过滤：如果包含大量参考文献标志词
        noise_keywords = ["参考文献", "References", "DOI:", "收稿日期", "作者简介"]
        # 如果“参考文献”出现在开头或占比较高，则视为噪音
        for kw in noise_keywords:
            if text.strip().startswith(kw) or text.count('[') > 5:
                return True
                
        return False

    def clean_text(self, text):
        """清洗文本内的微小噪音（如页码、多余空格）"""
        # 去除页码标记 (如 - 12 -)
        text = re.sub(r'-\s\d+\s-', '', text)
        # 合并多余换行符
        text = re.sub(r'\n+', '\n', text)
        return text.strip()