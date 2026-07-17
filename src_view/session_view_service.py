from pathlib import Path

from log_data_io import ensure_extracted_main as io_ensure_extracted_main
from log_data_io import load_events as io_load_events
from log_data_io import load_subagent_entries as io_load_subagent_entries
from session_log_processor import calc_credits as proc_calc_credits
from session_log_processor import collect_session_summaries as proc_collect_session_summaries
from session_log_processor import extract_session_title as proc_extract_session_title
from session_log_processor import group_blocks as proc_group_blocks
from session_log_processor import parse_session_datetime as proc_parse_session_datetime


def load_subagent_entries(path: Path) -> list:
    return io_load_subagent_entries(
        path,
        load_events_fn=io_load_events,
        group_blocks_fn=proc_group_blocks,
        extract_session_title_fn=proc_extract_session_title,
        calc_credits_fn=proc_calc_credits,
    )


def collect_session_summaries(date_str: str, finder_script: Path) -> tuple[list, str]:
    return proc_collect_session_summaries(
        date_str,
        finder_script,
        ensure_extracted_main_fn=io_ensure_extracted_main,
        load_events_fn=io_load_events,
        load_subagent_entries_fn=load_subagent_entries,
        group_blocks_fn=proc_group_blocks,
        extract_session_title_fn=proc_extract_session_title,
        calc_credits_fn=proc_calc_credits,
        parse_session_datetime_fn=proc_parse_session_datetime,
    )
