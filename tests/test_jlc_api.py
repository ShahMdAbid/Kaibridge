"""Unit and integration tests for the JLCPCB Sourcing Intelligence & CAD Fetcher Engine."""
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from kaibridge.sourcing.jlc_api import (
    fetch_cli_main,
    fetch_component_cad,
    query_jlcpcb_component,
)
from kaibridge.sourcing.check_cli import main as check_main


class TestJLCSourcingAPI:
    def test_query_invalid_lcsc_format(self):
        res = query_jlcpcb_component("INVALID_PART")
        assert not res["success"]
        assert "Invalid LCSC ID" in res["error"]

    def test_query_empty_id(self):
        res = query_jlcpcb_component("")
        assert not res["success"]
        assert "Invalid LCSC ID" in res["error"]

    @patch("urllib.request.urlopen")
    def test_query_successful_basic_part(self, mock_urlopen):
        mock_response_data = {
            "code": 200,
            "data": {
                "componentPageInfo": {
                    "list": [
                        {
                            "componentCode": "C6186",
                            "componentName": "AMS1117-3.3",
                            "componentModelEn": "AMS1117-3.3",
                            "componentBrandEn": "AMS",
                            "componentSpecificationEn": "SOT-223",
                            "componentTypeEn": "LDO",
                            "stockCount": 1400000,
                            "componentLibraryType": "base",
                            "dataManualUrl": "https://example.com/ams1117.pdf",
                            "lcscGoodsUrl": "https://lcsc.com/product/C6186.html",
                            "componentPrices": [
                                {"startNumber": 1, "productPrice": 0.2176},
                                {"startNumber": 50, "productPrice": 0.1718},
                            ],
                            "attributes": [
                                {"attribute_name_en": "Output Voltage", "attribute_value_name": "3.3V"}
                            ],
                        }
                    ]
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = query_jlcpcb_component("C6186")
        assert res["success"]
        assert res["lcsc"] == "C6186"
        assert res["in_stock"] is True
        assert res["stock"] == 1400000
        assert res["is_basic"] is True
        assert res["type"] == "Basic"
        assert res["unit_price_usd"] == 0.2176
        assert len(res["price_breaks"]) == 2
        assert res["datasheet"] == "https://example.com/ams1117.pdf"
        assert len(res["attributes"]) == 1

    @patch("urllib.request.urlopen")
    def test_query_stockout_extended_part(self, mock_urlopen):
        mock_response_data = {
            "code": 200,
            "data": {
                "componentPageInfo": {
                    "list": [
                        {
                            "componentCode": "C99999",
                            "componentName": "Rare Chip",
                            "stockCount": 0,
                            "componentLibraryType": "expand",
                            "dataManualUrl": "",
                            "lcscGoodsUrl": "https://lcsc.com/product/C99999.html",
                            "componentPrices": [],
                        }
                    ]
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = query_jlcpcb_component("C99999")
        assert res["success"]
        assert res["in_stock"] is False
        assert res["stock"] == 0
        assert res["is_basic"] is False
        assert res["type"] == "Extended"
        assert res["datasheet"] == "https://lcsc.com/product/C99999.html"

    @patch("urllib.request.urlopen")
    def test_query_not_found(self, mock_urlopen):
        mock_response_data = {
            "code": 200,
            "data": {
                "componentPageInfo": {
                    "list": []
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = query_jlcpcb_component("C000000")
        assert not res["success"]
        assert "not found" in res["error"]
        assert res["in_stock"] is False


class TestCADFetcher:
    @patch("subprocess.run")
    def test_fetch_primary_success(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="Downloaded OK", stderr="")
        res = fetch_component_cad("C6186", output_dir=tmp_path, prefer_jlc2kicad=True)
        assert res["success"]
        assert res["engine"] == "JLC2KiCadLib"
        assert mock_run.call_count == 1

    @patch("subprocess.run")
    def test_fetch_fallback_to_easyeda(self, mock_run, tmp_path):
        # 1st call fails (JLC2KiCadLib), 2nd call succeeds (easyeda2kicad)
        fail_res = MagicMock(returncode=1, stdout="", stderr="JLC2KiCadLib error")
        succ_res = MagicMock(returncode=0, stdout="easyeda success", stderr="")
        mock_run.side_effect = [fail_res, succ_res]

        res = fetch_component_cad("C165948", output_dir=tmp_path, prefer_jlc2kicad=True)
        assert res["success"]
        assert "fallback" in res["engine"]
        assert mock_run.call_count == 2

    @patch("subprocess.run")
    def test_fetch_both_fail(self, mock_run, tmp_path):
        fail_res1 = MagicMock(returncode=1, stdout="", stderr="JLC error")
        fail_res2 = MagicMock(returncode=1, stdout="", stderr="EasyEDA error")
        mock_run.side_effect = [fail_res1, fail_res2]

        res = fetch_component_cad("C88888", output_dir=tmp_path, prefer_jlc2kicad=True)
        assert not res["success"]
        assert res["engine"] == "None"
        assert "failed" in res["error"]


class TestCLISourcingCommands:
    def test_check_cli_help(self, capsys):
        from kaibridge.cli import main as cli_main
        code = cli_main(["check", "--help"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Query live JLCPCB warehouse inventory" in captured.out

    @patch("kaibridge.sourcing.check_cli.query_jlcpcb_component")
    def test_check_cli_json_output(self, mock_query, capsys):
        mock_query.return_value = {
            "success": True,
            "lcsc": "C6186",
            "name": "AMS1117-3.3",
            "stock": 100,
            "in_stock": True,
            "type": "Basic",
            "is_basic": True,
            "unit_price_usd": 0.2,
            "datasheet": "http://example.com/ds.pdf",
        }
        code = check_main(["C6186", "--json"])
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, dict)
        assert data["lcsc"] == "C6186"
        assert data["stock"] == 100

    def test_fetch_cli_help(self, capsys):
        from kaibridge.cli import main as cli_main
        code = cli_main(["fetch", "--help"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Pre-flight stock verification" in captured.out
