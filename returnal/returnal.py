"""Returnal test script"""
import os
import logging
from subprocess import Popen
import sys
import time
import pydirectinput as user

from returnal_utils import get_resolution, remove_intro_videos, get_args

sys.path.insert(1, os.path.join(sys.path[0], '..'))

# pylint: disable=wrong-import-position

from harness_utils.keras_service import KerasService
from harness_utils.logging import (
    format_resolution,
    seconds_to_milliseconds,
    setup_log_directory,
    write_report_json,
    DEFAULT_LOGGING_FORMAT,
    DEFAULT_DATE_FORMAT,
)
from harness_utils.process import terminate_processes
from harness_utils.steam import (
  get_run_game_id_command,
  DEFAULT_EXECUTABLE_PATH as STEAM_PATH,
  DEFAULT_STEAMAPPS_COMMON_PATH
)

# pylint: enable=wrong-import-position

STEAM_GAME_ID = 1649240
SCRIPT_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
LOG_DIRECTORY = os.path.join(SCRIPT_DIRECTORY, "run")
PROCESS_NAME = "Returnal"
LOCAL_USER_SETTINGS = f"{os.getenv('LOCALAPPDATA')}\\Returnal\\Steam\\Saved\\Config\\WindowsNoEditor\\GameUserSettings.ini"
VIDEO_PATH = os.path.join(DEFAULT_STEAMAPPS_COMMON_PATH, "Returnal", "Returnal", "Content", "Movies")

user.FAILSAFE = False

skippable_videos = [
    os.path.join(VIDEO_PATH, "Logos_PC.mp4"),
    os.path.join(VIDEO_PATH, "Logos_PC_UW21.mp4"),
    os.path.join(VIDEO_PATH, "Logos_PC_UW32.mp4"),
    os.path.join(VIDEO_PATH, "Logos_Short_PC.mp4"),
    os.path.join(VIDEO_PATH, "Logos_Short_PC_UW21.mp4"),
    os.path.join(VIDEO_PATH, "Logos_Short_PC_UW32.mp4"),
]


def start_game() -> None:
    """Start game via steam command"""
    steam_run_arg = get_run_game_id_command(STEAM_GAME_ID)
    logging.info("%s %s", STEAM_PATH, steam_run_arg)
    return Popen([STEAM_PATH, steam_run_arg])


def check_vram_alert(attempts: int) -> bool:
    """Look for VRAM alert in menu"""
    logging.info("Checking for VRAM alert prompt")
    for _ in range(attempts):
        alert_result = kerasService.capture_screenshot_find_word("alert")
        locate_result = kerasService.capture_screenshot_find_word("locate")
        if locate_result is not None:
            return False
        if alert_result is not None:
            return True
        time.sleep(2)

    return False


def escape_vram_alert():
    """Navigate VRAM alert"""
    user.keyDown("space")
    time.sleep(4)
    user.keyUp("space")


def await_game_start(attempts: int) -> bool:
    """Wait for game to start to open menu"""
    logging.info("Waiting for game to be ready to open menu")
    for _ in range(attempts):
        result = kerasService.capture_screenshot_find_word("locate")
        if result is not None:
            return True
        time.sleep(5)

    return False  


def navigate_options_menu() -> None:
    """Simulate inputs to navigate to options menu"""
    logging.info("Navigating to options menu")
    user.press("esc")
    user.press("enter")
    user.press("q")
    user.keyDown("tab")
    time.sleep(5)
    user.keyUp("tab")


def await_benchmark_menu(attempts: int) -> bool:
    """Wait to find the benchmark menu in the options"""
    logging.info("Waiting for in-game benchmark results")
    for _ in range(attempts):
        result = kerasService.capture_screenshot_find_word("benchmark")
        if result is not None:
            return True
        time.sleep(5)

    return False


def run_benchmark() -> tuple[float]:
    """Run the benchmark"""
    logging.info("Removing intro videos")
    remove_intro_videos(skippable_videos)

    logging.info("Starting game")
    start_game()
    setup_start_time = time.time()

    time.sleep(10)

    # Check if GPU has too little v ram and skip alert
    alert_found = check_vram_alert(7)

    if alert_found:
        escape_vram_alert()

    # Make sure the game started correctly
    game_started = await_game_start(10)

    if not game_started:
        logging.info("Could not find prompt to open menu!")
        sys.exit(1)

    # Navigate to in-game benchmark and start it
    navigate_options_menu()

    setup_end_time = time.time()
    elapsed_setup_time = round((setup_end_time - setup_start_time), 2)
    logging.info("Setup took %s seconds", elapsed_setup_time)

    test_start_time = time.time()

    # Wait for benchmark to complete
    time.sleep(120)

    # Wait for results screen to display info
    benchmark_menu_found = await_benchmark_menu(12)

    if not benchmark_menu_found:
        logging.info(
            "Results screen was not found! Did harness not wait long enough? Or test was too long?")
        sys.exit(1)

    test_end_time = time.time()
    elapsed_test_time = round((test_end_time - test_start_time), 2)
    logging.info("Benchmark took %s seconds", elapsed_test_time)

    terminate_processes(PROCESS_NAME)
    return start_time, end_time


setup_log_directory(LOG_DIRECTORY)

logging.basicConfig(filename=f'{LOG_DIRECTORY}/harness.log',
                    format=DEFAULT_LOGGING_FORMAT,
                    datefmt=DEFAULT_DATE_FORMAT,
                    level=logging.DEBUG)
console = logging.StreamHandler()
formatter = logging.Formatter(DEFAULT_LOGGING_FORMAT)
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

args = get_args()
kerasService = KerasService(
    args.keras_host, args.keras_port, os.path.join(LOG_DIRECTORY, "screenshot.jpg"))

try:
    start_time, end_time = run_benchmark()
    height, width = get_resolution(LOCAL_USER_SETTINGS)
    report = {
        "resolution": format_resolution(width, height),
        "start_time": seconds_to_milliseconds(start_time),
        "end_time": seconds_to_milliseconds(end_time)
    }

    write_report_json(LOG_DIRECTORY, "report.json", report)

#pylint: disable=broad-exception-caught
except Exception as e:
    logging.error("Something went wrong running the benchmark!")
    logging.exception(e)
    terminate_processes(PROCESS_NAME)
    sys.exit(1)
