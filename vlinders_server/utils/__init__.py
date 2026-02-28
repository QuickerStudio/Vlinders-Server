"""
日志工具模块
"""
import logging
import sys
from typing import Optional


def setup_logger(
    name: str = "vlinders_server",
    level: str = "INFO",
    format_string: Optional[str] = None
) -> logging.Logger:
    """设置日志记录器"""

    if format_string is None:
        format_string = (
            "%(asctime)s - %(name)s - %(levelname)s - "
            "%(filename)s:%(lineno)d - %(message)s"
        )

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))

    formatter = logging.Formatter(format_string)
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger


# 全局日志实例
logger = setup_logger()
