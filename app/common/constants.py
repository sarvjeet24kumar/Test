"""
Application Constants

Single source of truth for magic strings, integers, field lengths,
WebSocket event types, Redis key prefixes, and pagination defaults.
"""


# ==================== Field Length Constants ====================

# Used in model String() columns and schema validators
MAX_LENGTH_NAME = 255          # user first/last name, list name, item name, tenant name
MAX_LENGTH_EMAIL = 255         # email addresses
MAX_LENGTH_PASSWORD = 255      # hashed password storage
MAX_LENGTH_TOKEN = 255         # JWT / invitation tokens
MAX_LENGTH_USERNAME = 100      # usernames
MAX_LENGTH_SLUG = 100          # tenant slugs
MAX_LENGTH_UUID_STR = 36       # UUID as string (token_blacklist.user_id)
MIN_LENGTH_PASSWORD = 8        # minimum password length for validation
MIN_ITEM_QUANTITY = 1          # minimum item quantity
MAX_CHAT_MESSAGE_LENGTH = 2000 # max characters for a single chat message


# ==================== Error Messages ====================

# Note: Generic error messages are kept as inline strings in services/APIs 
# to avoid over-engineering, unless they are truly shared across many files.



# ==================== WebSocket Event Types ====================

WS_EVENT_ITEM_ADDED = "item_added"
WS_EVENT_ITEM_UPDATED = "item_updated"
WS_EVENT_ITEM_DELETED = "item_deleted"
WS_EVENT_MEMBER_JOINED = "member_joined"
WS_EVENT_MEMBER_REMOVED = "member_removed"
WS_EVENT_MEMBER_LEFT = "member_left"
WS_EVENT_INVITE_CREATED = "invite_created"
WS_EVENT_INVITE_ACCEPTED = "invite_accepted"
WS_EVENT_INVITE_REJECTED = "invite_rejected"
WS_EVENT_INVITE_CANCELLED = "invite_cancelled"
WS_EVENT_LIST_UPDATED = "list_updated"
WS_EVENT_LIST_DELETED = "list_deleted"
WS_EVENT_CHAT_MESSAGE = "chat_message"
WS_EVENT_PERMISSIONS_UPDATED = "permissions_updated"


# ==================== WebSocket Message Types ====================

WS_TYPE_CONNECTED = "connected"
WS_TYPE_SUBSCRIBE = "subscribe"
WS_TYPE_SUBSCRIBED = "subscribed"
WS_TYPE_UNSUBSCRIBE = "unsubscribe"
WS_TYPE_UNSUBSCRIBED = "unsubscribed"
WS_TYPE_PING = "ping"
WS_TYPE_PONG = "pong"
WS_TYPE_ERROR = "error"
WS_TYPE_CHAT_MESSAGE = "chat_message"


# ==================== WebSocket Close Codes ====================

WS_CLOSE_AUTH_FAILED = 4001
WS_CLOSE_FORBIDDEN = 4003


# ==================== Redis Key Prefixes ====================

REDIS_PREFIX_OTP = "otp"
REDIS_PREFIX_INVITE = "invite"
REDIS_PREFIX_BLACKLIST = "blacklist"
REDIS_PREFIX_BLACKLIST_ACCESS = "blacklist:access"
REDIS_PREFIX_PASSWORD_RESET = "password_reset"


# ==================== Redis Channel Prefixes ====================

REDIS_CHANNEL_LIST = "list"


# ==================== Pagination ====================

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MIN_PAGE_SIZE = 1
DEFAULT_CHAT_LIMIT = 50
MAX_CHAT_LIMIT = 100
MIN_CHAT_LIMIT = 1


# ==================== Password Validation ====================

PASSWORD_MIN_LENGTH = 8
PASSWORD_REQUIRE_UPPERCASE = True
PASSWORD_REQUIRE_LOWERCASE = True
PASSWORD_REQUIRE_DIGIT = True


# ==================== Token Types ====================

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
TOKEN_TYPE_INVITE = "invitation"
TOKEN_TYPE_PASSWORD_RESET = "password_reset"
