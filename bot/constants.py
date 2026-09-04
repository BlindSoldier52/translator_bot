MAX_AUTH_ATTEMPTS = 3
LANGUAGE_AUTO_DETECT_SAMPLE_THRESHOLD = 20
ADMIN_RECHECK_INTERVAL_SECONDS = 600
LOGIN_ATTEMPT_PRUNE_INTERVAL_SECONDS = 3600
MAX_CONCURRENT_UPDATES = 32
DETECTION_CONFIDENCE_SKIP_THRESHOLD = 0.4

AUTO_DETECT_CODE = "auto"

FLOW_REGISTER = "register"
FLOW_GROUP_AUTH = "group_auth"
FLOW_FEEDBACK = "feedback"
FLOW_SET_API_KEY = "set_api_key"
FLOW_FILE_SETTINGS = "file_settings"
FLOW_FILE_TRANSLATE_LANGUAGE = "file_translate_language"
FLOW_SET_LANGUAGE = "set_language"
FLOW_IMAGE_TRANSLATE_LANGUAGE = "image_translate_language"

STEP_USERNAME = "username"
STEP_PASSWORD = "password"
STEP_FEEDBACK_MESSAGE = "feedback_message"
STEP_API_KEY_PROVIDER = "api_key_provider"
STEP_API_KEY_VALUE = "api_key_value"
STEP_LANGUAGE_CHOICE = "language_choice"
STEP_FILE_TARGET = "file_target"
STEP_FILE_CHOICE = "file_choice"
STEP_FILE_SECTION = "file_section"
STEP_FILE_OUTPUT_MODE = "file_output_mode"
STEP_FILE_LIMIT_MODE = "file_limit_mode"
STEP_IMAGE_MAX_SIZE = "image_max_size"
STEP_IMAGE_OUTPUT_MODE = "image_output_mode"
STEP_IMAGE_LIMIT_MODE = "image_limit_mode"
STEP_IMAGE_DAILY_LIMIT = "image_daily_limit"
STEP_IMAGE_LANGUAGE = "image_language"
STEP_FILE_EXTENSIONS = "file_extensions"
STEP_FILE_MAX_SIZE = "file_max_size"
STEP_FILE_DAILY_LIMIT = "file_daily_limit"
STEP_FILE_LANGUAGE = "file_language"

FILE_OUTPUT_MODE_TEXT = "text"
FILE_OUTPUT_MODE_FILE = "file"

IMAGE_OUTPUT_MODE_TEXT = "text"
IMAGE_OUTPUT_MODE_OVERLAY = "overlay"
IMAGE_OUTPUT_MODE_BOTH = "both"

# What each Bot API can actually carry, for validating MAX_FILE_SIZE_MB.
CLOUD_BOT_API_MAX_FILE_MB = 20
LOCAL_BOT_API_MAX_FILE_MB = 2000

TELEGRAM_MESSAGE_LIMIT = 4096

# Downloading hundreds of megabytes needs far longer than the default 5s read.
FILE_TRANSFER_TIMEOUT_SECONDS = 600

DEFAULT_MAINTENANCE_MESSAGE = (
	"I'm down for maintenance right now, back to translating again soon. Thanks for your patience!"
)

ANNOUNCEMENT_POLL_INTERVAL_SECONDS = 60
ANNOUNCEMENT_SEND_THROTTLE_SECONDS = 0.05
ANNOUNCEMENT_MAX_ATTEMPTS = 3
FEEDBACK_MAX_LEN = 10000
