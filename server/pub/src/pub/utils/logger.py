"""
Logger configuration
"""
import os

import logging
import logging.config

import os
import logging
import logging.config


class ColorFormatter(logging.Formatter):
     """ANSI color formatter for console logs."""
 
     COLORS = {
         logging.DEBUG: "\033[36m",  # cyan
         logging.INFO: "\033[32m",  # green
         logging.WARNING: "\033[33m",  # yellow
         logging.ERROR: "\033[31m",  # red
         logging.CRITICAL: "\033[1;31m",  # bold red
     }
     RESET = "\033[0m"
 
     def format(self, record: logging.LogRecord) -> str:
         message = super().format(record)
         color = self.COLORS.get(record.levelno)
         if not color:
             return message
         return f"{color}{message}{self.RESET}"
 

class SpringBootFormatter(logging.Formatter):
    """复刻 Spring Boot 风格的日志格式化器 (文件名颜色跟随日志级别)"""

    # 级别颜色
    LEVEL_COLORS = {
        logging.DEBUG: "\033[30m",       # Cyan (青色)
        # logging.DEBUG: "\033[36m",       # Cyan (青色)
        # logging.INFO: "\033[32m",        # Green (绿色)
        logging.INFO: "\033[36m",        # Green (绿色)
        logging.WARNING: "\033[33m",     # Yellow (黄色)
        logging.ERROR: "\033[31m",       # Red (红色)
        logging.CRITICAL: "\033[1;31m",  # Bold Red (加粗红色)
    }

    # 局部组件颜色
    DIM = "\033[90m"     # Dark Gray (暗灰色，用于时间和分隔符)
    RESET = "\033[0m"    # 颜色重置

    def format(self, record: logging.LogRecord) -> str:
        # 1. 格式化时间 (暗灰色)
        asctime = self.formatTime(record, self.datefmt)
        time_part = f"{self.DIM}{asctime}{self.RESET}"
        
        # 获取当前日志级别的颜色，如果找不到则默认无色
        level_color = self.LEVEL_COLORS.get(record.levelno, "")
        
        # 2. 格式化级别 (自带对应颜色，固定占据 7 个字符宽度对齐)
        level_part = f"{level_color}{record.levelname:<7}{self.RESET}"
        
        
        # 3. 格式化代码位置 
        location = f"{record.module}:{record.lineno}"
        location_part = f"{level_color}{location:>0}{self.RESET}"
        
        
        # 4. 日志正文主体 (默认终端白/灰)
        message = record.getMessage()
        message = f"{self.DIM}{message}{self.RESET}"
        
        # 5. 拼装成 Spring Boot 经典排版格式
        return f"{time_part} {level_part}{self.DIM}{self.RESET}[{location_part}]: {message}"
  
class ExcludeFileFilter(logging.Filter):
    """自定义过滤器：屏蔽特定文件产生的日志"""
    def filter(self, record: logging.LogRecord) -> bool:
        # 只要文件名是以 "_" 开头的（比如 _trace.py, _config.py, _client.py），统统拦截！
        if record.filename.startswith("_"):
            return False
        return True
    
def setup_logging(environment: str = "development", debug: bool = True):
    """Configure application logging."""
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
            "colored": {
                # 把这里指向新的 SpringBootFormatter
                "()": "pub.utils.logger.SpringBootFormatter",
                # 注意：因为我们在类里已经写死了拼装逻辑，这里的 format 参数可以保留也可删除，不影响输出了
                # "datefmt": '%m-%d %H:%M:%S'
                "datefmt": '%H:%M:%S'
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            },
        },
        # 新增 filters 配置块
        "filters": {
            "exclude_trace": {
                # 指向你刚刚写的过滤器类的路径
                "()": "pub.utils.logger.ExcludeFileFilter"
            }
        },
        
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG" if debug else "INFO",
                "formatter": "colored",
                "stream": "ext://sys.stdout",
                # 给控制台加上这个过滤器
                "filters": ["exclude_trace"], 
            },
            "file": {
                "class": "logging.FileHandler",
                "level": "DEBUG",
                "formatter": "detailed",
                "filename": "logs/app.log",
                # 如果你想让文件里也不要记录，也加上它
                "filters": ["exclude_trace"], 
            },
        },
        "loggers": {
            "sqlalchemy.engine": {
                "level": "WARNING",
                "propagate": False
            },
            "sqlalchemy.pool": {
                "level": "WARNING",
                "propagate": False
            },
            # --- 新增：强制接管 Uvicorn 服务器日志 ---
            "uvicorn": {
                "handlers": ["console", "file"], # 强行绑定你的彩色控制台和文件
                "level": "INFO",
                "propagate": False               # 阻止双重打印
            },
            "uvicorn.error": {
                "level": "INFO",
                "propagate": True                # 错误日志交给父级 uvicorn 处理即可
            },
            "uvicorn.access": {
                "handlers": ["console", "file"], # 强行绑定你的彩色控制台和文件
                "level": "INFO",
                "propagate": False               # 阻止它用自带的格式输出
            },
        },
        "root": {
            "level": "DEBUG" if debug else "INFO",
            "handlers": ["console", "file"],
        },
    }

    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.config.dictConfig(logging_config)
    logger = logging.getLogger(__name__)
    return logger