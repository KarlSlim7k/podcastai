"""Tests for the logger utility."""
import pytest
import logging
from pathlib import Path


def test_setup_logging_creates_log_file(tmp_path):
    from app import config as cfg
    from app.utils.logger import setup_logging

    original_logs_dir = cfg.settings.logs_dir
    cfg.settings.logs_dir = tmp_path
    try:
        # Reset root logger handlers so basicConfig can re-run
        root = logging.getLogger()
        root.handlers.clear()
        setup_logging()
        # Should have created a file handler pointing to tmp_path
        log_files = list(tmp_path.glob("app_*.log"))
        assert len(log_files) >= 1
    finally:
        cfg.settings.logs_dir = original_logs_dir
        # Clean up handlers to avoid duplicates in other tests
        root = logging.getLogger()
        root.handlers.clear()


def test_get_logger_returns_logger():
    from app.utils.logger import get_logger
    log = get_logger("test_module")
    assert log is not None


def test_setup_logging_debug_mode(tmp_path):
    from app import config as cfg
    from app.utils.logger import setup_logging

    original_logs = cfg.settings.logs_dir
    original_debug = cfg.settings.debug
    cfg.settings.logs_dir = tmp_path
    cfg.settings.debug = True
    try:
        root = logging.getLogger()
        root.handlers.clear()
        setup_logging()
        assert logging.getLogger().level == logging.DEBUG
    finally:
        cfg.settings.logs_dir = original_logs
        cfg.settings.debug = original_debug
        root = logging.getLogger()
        root.handlers.clear()
