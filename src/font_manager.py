import os
import logging
import shutil
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

class FontManager:
    DEFAULT_FONT = 'Helvetica'
    
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.fonts_dir = os.path.join(self.base_dir, "fonts")
        self.simhei_path = os.path.join(self.fonts_dir, "simhei.ttf")
        self.initialized = False
        
    def ensure_font_directory(self):
        """Ensure font directory exists"""
        os.makedirs(self.fonts_dir, exist_ok=True)
        
    def get_system_font(self):
        """Find suitable Chinese font from system"""
        system_font_paths = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "C:\\Windows\\Fonts\\simhei.ttf",
            "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc"
        ]
        
        for font_path in system_font_paths:
            if os.path.exists(font_path):
                return font_path
        return None
        
    def initialize(self):
        """Initialize font system"""
        if self.initialized:
            return True
            
        try:
            self.ensure_font_directory()
            
            # If Chinese font doesn't exist, try to copy from system
            if not os.path.exists(self.simhei_path):
                system_font = self.get_system_font()
                if system_font:
                    shutil.copy2(system_font, self.simhei_path)
                    logging.info(f"Copied system font: {system_font} -> {self.simhei_path}")
                else:
                    logging.warning("No suitable Chinese font found in system")
                    return False
            
            # Register font
            if os.path.exists(self.simhei_path):
                pdfmetrics.registerFont(TTFont('SimHei', self.simhei_path))
                self.initialized = True
                logging.info("Successfully registered SimHei font")
                return True
                
        except Exception as e:
            logging.error(f"Font initialization failed: {e}")
            
        return False
        
    def get_font_name(self):
        """Get font name to use"""
        return 'SimHei' if self.initialized else self.DEFAULT_FONT
