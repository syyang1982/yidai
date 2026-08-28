"""Tests for src/report/company_report.py — 个股深度报告。"""

import os
import tempfile

import pytest

from src.report.company_report import generate_company_report


@pytest.fixture
def output_dir():
    """Temp directory for report output."""
    d = tempfile.mkdtemp()
    yield d
    # cleanup
    import shutil
    shutil.rmtree(d, ignore_errors=True)


class TestGenerateCompanyReport:
    def test_generates_file(self, output_dir):
        """Report file should be created even with no data."""
        path = generate_company_report(
            ticker="01810.HK",
            db_path=":memory:",
            kb_dir="/nonexistent",
            signal_db_path=":memory:",
            output_dir=output_dir,
        )
        assert os.path.exists(path)
        assert path.endswith(".md")
        content = open(path, encoding="utf-8").read()
        assert "01810.HK" in content

    def test_report_has_sections(self, output_dir):
        """Report should contain all major section headers."""
        path = generate_company_report(
            ticker="01810.HK",
            db_path=":memory:",
            kb_dir="/nonexistent",
            signal_db_path=":memory:",
            output_dir=output_dir,
        )
        content = open(path, encoding="utf-8").read()
        assert "## 一、公司概况" in content
        assert "## 二、七维评分" in content
        assert "## 三、财务异常预警" in content
        assert "## 四、决策历史" in content
        assert "## 五、信号历史" in content
        assert "## 六、投资论点与风险" in content
        assert "## 七、回报预期" in content
        assert "## 八、行业对比" in content

    def test_report_has_header(self, output_dir):
        """Report header should contain ticker and date."""
        path = generate_company_report(
            ticker="09988.HK",
            db_path=":memory:",
            kb_dir="/nonexistent",
            signal_db_path=":memory:",
            output_dir=output_dir,
        )
        content = open(path, encoding="utf-8").read()
        assert "09988.HK" in content
        assert "深度分析报告" in content

    def test_report_has_disclaimer(self, output_dir):
        """Report should end with disclaimer."""
        path = generate_company_report(
            ticker="01810.HK",
            db_path=":memory:",
            kb_dir="/nonexistent",
            signal_db_path=":memory:",
            output_dir=output_dir,
        )
        content = open(path, encoding="utf-8").read()
        assert "不构成投资建议" in content

    def test_empty_data_graceful(self, output_dir):
        """With no data, report should still render with placeholder text."""
        path = generate_company_report(
            ticker="NONEXIST.HK",
            db_path=":memory:",
            kb_dir="/nonexistent",
            signal_db_path=":memory:",
            output_dir=output_dir,
        )
        content = open(path, encoding="utf-8").read()
        assert "暂无" in content or "数据不足" in content or "未检测到" in content

    def test_a_share_ticker(self, output_dir):
        """A-share ticker should be handled."""
        path = generate_company_report(
            ticker="002415.SZ",
            db_path=":memory:",
            kb_dir="/nonexistent",
            signal_db_path=":memory:",
            output_dir=output_dir,
        )
        content = open(path, encoding="utf-8").read()
        assert "002415.SZ" in content

    def test_filename_format(self, output_dir):
        """Filename should contain sanitized ticker and date."""
        path = generate_company_report(
            ticker="01810.HK",
            db_path=":memory:",
            kb_dir="/nonexistent",
            signal_db_path=":memory:",
            output_dir=output_dir,
        )
        filename = os.path.basename(path)
        assert "company_01810_HK" in filename
        assert filename.endswith(".md")
