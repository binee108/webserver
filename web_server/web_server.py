"""웹 서버 루트 패키지 호환 래퍼"""

from __future__ import annotations

import importlib
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent)]

# 기존 구조에서 사용하던 app 패키지를 그대로 노출
app = importlib.import_module('app')

__all__ = ['app']
