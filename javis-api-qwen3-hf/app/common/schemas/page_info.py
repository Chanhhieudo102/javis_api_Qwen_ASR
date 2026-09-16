"""Pagination info schema."""

from pydantic import BaseModel, Field


class PageInfo(BaseModel):
    """Pagination information model."""

    current_page: int = Field(1, description="The current page number")
    next_page: int = Field(1, description="The next page number")
    prev_page: int = Field(1, description="The previous page number")
    total_pages: int = Field(1, description="The total number of pages")
    total_count: int = Field(0, description="The total number of items")

    def __init__(
        self,
        current_page: int = 1,
        total_pages: int = 1,
        total_count: int = 0,
        **data,
    ):
        prev_page = current_page - 1 if current_page > 1 else 1
        next_page = current_page + 1 if current_page < total_pages else total_pages

        super().__init__(
            current_page=current_page,
            prev_page=prev_page,
            next_page=next_page,
            total_pages=total_pages,
            total_count=total_count,
            **data,
        )

    @staticmethod
    def create_page_info(
        current_page: int = 1, page_size: int = 10, total_count: int = 0
    ) -> "PageInfo":
        """Create a PageInfo instance for pagination."""
        total_pages = (total_count + page_size - 1) // page_size or 1
        return PageInfo(
            current_page=current_page,
            total_pages=total_pages,
            total_count=total_count,
        )
