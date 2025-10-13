#!/usr/bin/env python3
"""
태깅 누락 분석 스크립트
프로젝트 내 모든 Python 파일을 스캔하여 @FEAT: 태그가 없는 클래스/함수를 찾습니다.
"""

import os
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

# 스캔 대상 디렉토리
PROJECT_ROOT = Path(__file__).parent / "web_server" / "app"

# 제외할 디렉토리/파일
EXCLUDE_DIRS = {"__pycache__", "migrations", ".pyc"}
EXCLUDE_FILES = {"__init__.py"}  # __init__.py는 별도 처리

# 기존 기능 태그 (FEATURE_CATALOG.md 기준)
KNOWN_FEATURES = {
    "webhook-order",
    "order-queue",
    "order-tracking",
    "position-tracking",
    "capital-management",
    "exchange-integration",
    "price-cache",
    "event-sse",
    "strategy-management",
    "analytics",
    "telegram-notification",
    "background-scheduler"
}


def extract_definitions(file_path: Path) -> List[Tuple[int, str, str]]:
    """
    파일에서 클래스/함수 정의를 추출
    Returns: [(line_number, type, name), ...]
    """
    definitions = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for i, line in enumerate(lines, start=1):
            # 클래스 정의
            class_match = re.match(r'^class\s+(\w+)', line)
            if class_match:
                definitions.append((i, 'class', class_match.group(1)))
                continue

            # 함수 정의 (메서드 포함)
            func_match = re.match(r'^(\s*)def\s+(\w+)\s*\(', line)
            if func_match:
                indent = func_match.group(1)
                func_name = func_match.group(2)
                # 인덴트로 메서드/함수 구분
                def_type = 'method' if indent else 'function'
                definitions.append((i, def_type, func_name))

    except Exception as e:
        print(f"⚠️  Error reading {file_path}: {e}")

    return definitions


def has_feat_tag(file_path: Path, line_num: int) -> bool:
    """
    특정 라인 위 5줄 이내에 @FEAT: 태그가 있는지 확인
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 5줄 위까지 검사
        start = max(0, line_num - 6)
        end = line_num - 1

        for line in lines[start:end]:
            if '@FEAT:' in line:
                return True

        return False

    except Exception as e:
        print(f"⚠️  Error checking tags in {file_path}: {e}")
        return False


def get_existing_tags(file_path: Path) -> set:
    """
    파일에서 사용된 모든 @FEAT: 태그 추출
    """
    tags = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            tags = set(re.findall(r'@FEAT:([a-z-]+)', content))
    except Exception as e:
        print(f"⚠️  Error extracting tags from {file_path}: {e}")

    return tags


def categorize_file(file_path: Path, existing_tags: set) -> str:
    """
    파일 분류:
    - framework: __init__.py, config, constants
    - existing-feature: 기존 12개 기능에 속함
    - new-feature: 새로운 미문서화 기능
    - utility: 범용 유틸리티
    """
    file_name = file_path.name

    # Framework/Boilerplate
    if file_name in ['__init__.py', 'constants.py', 'config.py']:
        return 'framework'

    # Exceptions
    if 'exception' in file_name.lower():
        return 'framework'

    # 기존 기능
    if existing_tags & KNOWN_FEATURES:
        return 'existing-feature'

    # 유틸리티
    if 'util' in str(file_path).lower() or 'helper' in file_name.lower():
        return 'utility'

    # Routes/Services는 대부분 기능
    if 'routes/' in str(file_path) or 'services/' in str(file_path):
        return 'new-feature'

    # Models
    if file_name == 'models.py':
        return 'framework'

    # Exchanges
    if 'exchanges/' in str(file_path):
        if existing_tags:
            return 'existing-feature'
        else:
            return 'new-feature'

    return 'unknown'


def analyze_project():
    """
    프로젝트 전체 분석
    """
    print("🔍 태깅 누락 분석 시작...\n")
    print(f"📂 스캔 디렉토리: {PROJECT_ROOT}\n")

    # 결과 저장
    untagged_items = defaultdict(list)
    file_stats = {
        'total_files': 0,
        'tagged_files': 0,
        'untagged_files': 0,
        'total_definitions': 0,
        'tagged_definitions': 0,
        'untagged_definitions': 0
    }

    category_stats = defaultdict(int)

    # 모든 Python 파일 스캔
    for py_file in sorted(PROJECT_ROOT.rglob("*.py")):
        # 제외 대상 확인
        if any(excluded in py_file.parts for excluded in EXCLUDE_DIRS):
            continue

        file_stats['total_files'] += 1
        relative_path = py_file.relative_to(PROJECT_ROOT.parent)

        # 파일에서 정의 추출
        definitions = extract_definitions(py_file)
        file_stats['total_definitions'] += len(definitions)

        # 파일의 기존 태그 추출
        existing_tags = get_existing_tags(py_file)
        file_category = categorize_file(py_file, existing_tags)
        category_stats[file_category] += 1

        # 태그 누락 확인
        untagged_in_file = []
        for line_num, def_type, def_name in definitions:
            file_stats['total_definitions'] += 1

            if has_feat_tag(py_file, line_num):
                file_stats['tagged_definitions'] += 1
            else:
                file_stats['untagged_definitions'] += 1
                untagged_in_file.append({
                    'line': line_num,
                    'type': def_type,
                    'name': def_name,
                    'category': file_category
                })

        # 파일 통계
        if existing_tags or any(has_feat_tag(py_file, d[0]) for d in definitions):
            file_stats['tagged_files'] += 1
        else:
            file_stats['untagged_files'] += 1

        # 태그 누락 항목 저장
        if untagged_in_file:
            untagged_items[str(relative_path)] = {
                'items': untagged_in_file,
                'existing_tags': existing_tags,
                'category': file_category
            }

    # 결과 출력
    print("=" * 80)
    print("📊 전체 통계")
    print("=" * 80)
    print(f"총 파일 수: {file_stats['total_files']}")
    print(f"  - 태그 있는 파일: {file_stats['tagged_files']}")
    print(f"  - 태그 없는 파일: {file_stats['untagged_files']}")
    print(f"\n총 정의 수 (클래스/함수): {file_stats['total_definitions']}")
    print(f"  - 태그 있음: {file_stats['tagged_definitions']}")
    print(f"  - 태그 없음: {file_stats['untagged_definitions']}")

    print(f"\n카테고리별 파일 분포:")
    for category, count in sorted(category_stats.items()):
        print(f"  - {category}: {count}개")

    print("\n" + "=" * 80)
    print("🏷️  태그 누락 항목 상세")
    print("=" * 80)

    # 카테고리별로 그룹화
    by_category = defaultdict(list)
    for file_path, data in untagged_items.items():
        by_category[data['category']].append((file_path, data))

    # 카테고리별 출력
    for category in ['existing-feature', 'new-feature', 'utility', 'framework', 'unknown']:
        if category not in by_category:
            continue

        print(f"\n### {category.upper().replace('-', ' ')}")
        print("-" * 80)

        for file_path, data in sorted(by_category[category]):
            print(f"\n📄 {file_path}")
            if data['existing_tags']:
                print(f"   기존 태그: {', '.join(sorted(data['existing_tags']))}")

            for item in data['items']:
                icon = "🔹" if item['type'] == 'class' else "  ▫️"
                print(f"   {icon} Line {item['line']:4d} | {item['type']:8s} | {item['name']}")

    # Markdown 리포트 생성
    generate_markdown_report(untagged_items, file_stats, category_stats)

    print("\n" + "=" * 80)
    print("✅ 분석 완료!")
    print("📝 상세 리포트: docs/UNTAGGED_CODE_ANALYSIS.md")
    print("=" * 80)


def generate_markdown_report(untagged_items: Dict, file_stats: Dict, category_stats: Dict):
    """
    Markdown 리포트 생성
    """
    report_path = Path(__file__).parent / "docs" / "UNTAGGED_CODE_ANALYSIS.md"
    report_path.parent.mkdir(exist_ok=True)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# 태깅 누락 분석 보고서\n\n")
        f.write(f"**생성일**: {Path(__file__).stat().st_mtime}\n\n")

        # Executive Summary
        f.write("## Executive Summary\n\n")
        f.write(f"- **총 파일**: {file_stats['total_files']}개\n")
        f.write(f"- **태그 있는 파일**: {file_stats['tagged_files']}개 ({file_stats['tagged_files']/file_stats['total_files']*100:.1f}%)\n")
        f.write(f"- **태그 없는 파일**: {file_stats['untagged_files']}개 ({file_stats['untagged_files']/file_stats['total_files']*100:.1f}%)\n\n")

        f.write(f"- **총 정의 (클래스/함수)**: {file_stats['total_definitions']}개\n")
        f.write(f"- **태그 있는 정의**: {file_stats['tagged_definitions']}개 ({file_stats['tagged_definitions']/file_stats['total_definitions']*100:.1f}%)\n")
        f.write(f"- **태그 없는 정의**: {file_stats['untagged_definitions']}개 ({file_stats['untagged_definitions']/file_stats['total_definitions']*100:.1f}%)\n\n")

        # 카테고리 통계
        f.write("## 카테고리별 파일 분포\n\n")
        f.write("| 카테고리 | 파일 수 | 비율 |\n")
        f.write("|---------|---------|------|\n")
        for category, count in sorted(category_stats.items()):
            pct = count / file_stats['total_files'] * 100
            f.write(f"| {category} | {count} | {pct:.1f}% |\n")

        # 카테고리별 상세
        f.write("\n## 태그 누락 항목 상세\n\n")

        by_category = defaultdict(list)
        for file_path, data in untagged_items.items():
            by_category[data['category']].append((file_path, data))

        for category in ['existing-feature', 'new-feature', 'utility', 'framework', 'unknown']:
            if category not in by_category:
                continue

            f.write(f"\n### {category.replace('-', ' ').title()}\n\n")

            # 조치 계획
            if category == 'existing-feature':
                f.write("**조치**: 기존 기능 태그 추가\n\n")
            elif category == 'new-feature':
                f.write("**조치**: 새 기능으로 문서화 + 태깅\n\n")
            elif category == 'utility':
                f.write("**조치**: `@FEAT:utility @COMP:util @TYPE:helper` 태그 추가\n\n")
            elif category == 'framework':
                f.write("**조치**: `@FEAT:framework @COMP:config @TYPE:boilerplate` 태그 추가\n\n")

            f.write("| 파일 | 라인 | 타입 | 이름 | 기존 태그 |\n")
            f.write("|------|------|------|------|----------|\n")

            for file_path, data in sorted(by_category[category]):
                tags_str = ', '.join(sorted(data['existing_tags'])) if data['existing_tags'] else '-'

                for item in data['items']:
                    f.write(f"| `{file_path}` | {item['line']} | {item['type']} | `{item['name']}` | {tags_str} |\n")

        # 다음 단계
        f.write("\n## 다음 단계\n\n")
        f.write("### Phase 1: 기존 기능 태깅 (High Priority)\n")
        f.write("- [ ] `existing-feature` 카테고리 항목에 적절한 @FEAT 태그 추가\n")
        f.write("- [ ] 기존 12개 기능 중 해당하는 기능 태그 사용\n\n")

        f.write("### Phase 2: 새 기능 문서화 (Medium Priority)\n")
        f.write("- [ ] `new-feature` 카테고리 항목 분석\n")
        f.write("- [ ] 독립적인 기능인 경우 FEATURE_CATALOG.md에 등록\n")
        f.write("- [ ] docs/features/{feature-name}.md 상세 문서 작성\n")
        f.write("- [ ] 태그 추가\n\n")

        f.write("### Phase 3: 유틸리티/프레임워크 태깅 (Low Priority)\n")
        f.write("- [ ] `utility` 카테고리: `@FEAT:utility` 태그 추가\n")
        f.write("- [ ] `framework` 카테고리: `@FEAT:framework` 태그 추가\n\n")

        f.write("### Phase 4: 데드코드 식별 (Optional)\n")
        f.write("- [ ] grep으로 각 함수/클래스 호출 위치 검색\n")
        f.write("- [ ] 사용되지 않는 코드 `@FEAT:dead-code` 태그 추가\n")
        f.write("- [ ] 제거 계획 수립\n")


if __name__ == "__main__":
    analyze_project()
