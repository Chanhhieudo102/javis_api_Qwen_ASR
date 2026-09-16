"""Error constants for the application.

All error constants should be defined here and grouped by module.
The constant value must match the key in error_en.yml (and other locale files).

Usage:
    from app.common.constants.error_constants import ErrorConstants
    raise BadRequestException(detail=ErrorConstants.Auth.OWNER_ALREADY_EXISTS)
"""


class ErrorConstants:
    """Error constants grouped by module."""

    # =========================================================================
    # COMMON / SYSTEM ERRORS
    # =========================================================================
    class System:
        """System-level error constants."""

        INTERNAL_SERVER_ERROR = "internal_server_error"
        BAD_REQUEST = "bad_request"
        NOT_FOUND = "not_found"

    # =========================================================================
    # AUTH MODULE
    # =========================================================================
    class Auth:
        """Authentication and authorization error constants."""

        UNAUTHORIZED = "unauthorized"
        FORBIDDEN = "forbidden"
        INVALID_CREDENTIALS = "invalid_credentials"
        TOKEN_EXPIRED = "token_expired"
        TOKEN_INVALID = "token_invalid"
        OWNER_ALREADY_EXISTS = "owner_already_exists"

    # =========================================================================
    # USER MODULE
    # =========================================================================
    class User:
        """User-related error constants."""

        USER_NOT_FOUND = "user_not_found"
        USER_ALREADY_EXISTS = "user_already_exists"
        EMAIL_ALREADY_EXISTS = "email_already_exists"
        USERNAME_ALREADY_EXISTS = "username_already_exists"
        CANNOT_CREATE_OWNER_AS_EMPLOYEE = "cannot_create_owner_as_employee"

    # =========================================================================
    # ZONE MODULE
    # =========================================================================
    class Zone:
        """Zone-related error constants."""

        ZONE_NOT_FOUND = "zone_not_found"

    # =========================================================================
    # TABLE MODULE
    # =========================================================================
    class Table:
        """Table-related error constants."""

        TABLE_NOT_FOUND = "table_not_found"
        TABLE_NUMBER_ALREADY_EXISTS = "table_number_already_exists"

    # =========================================================================
    # MENU CATEGORY MODULE
    # =========================================================================
    class MenuCategory:
        """Menu category-related error constants."""

        CATEGORY_NOT_FOUND = "category_not_found"
        CATEGORY_NAME_ALREADY_EXISTS = "category_name_already_exists"

    # =========================================================================
    # MENU ITEM MODULE
    # =========================================================================
    class MenuItem:
        """Menu item-related error constants."""

        MENU_ITEM_NOT_FOUND = "menu_item_not_found"
        MENU_ITEM_NOT_AVAILABLE = "menu_item_not_available"

    # =========================================================================
    # ORDER ITEM MODULE
    # =========================================================================
    class OrderItem:
        """Order item-related error constants."""

        ORDER_ITEM_NOT_FOUND = "order_item_not_found"
        CANNOT_UPDATE_CANCELLED_ORDER = "cannot_update_cancelled_order"
        INVALID_QUANTITY = "invalid_quantity"
        INVALID_STATUS_TRANSITION = "invalid_status_transition"
        ORDER_ALREADY_CANCELLED = "order_already_cancelled"
        CANNOT_CANCEL_SERVED_ORDER = "cannot_cancel_served_order"
        CAN_ONLY_DELETE_PENDING_ORDER = "can_only_delete_pending_order"

    # =========================================================================
    # ORDER MODULE
    # =========================================================================
    class Order:
        """Order-related error constants."""

        ORDER_NOT_FOUND = "order_not_found"
        NO_OPEN_ORDER_FOR_TABLE = "no_open_order_for_table"
        ORDER_HAS_NO_ITEMS = "order_has_no_items"

    # =========================================================================
    # BILL MODULE
    # =========================================================================
    class Bill:
        """Bill-related error constants."""

        BILL_NOT_FOUND = "bill_not_found"
        CANNOT_DELETE_PAID_BILL = "cannot_delete_paid_bill"
        CANNOT_UPDATE_PAID_BILL = "cannot_update_paid_bill"
