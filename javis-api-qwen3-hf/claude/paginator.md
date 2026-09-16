# Paginator Documentation

This document describes the standard pagination pattern used across all API endpoints that return lists of items.

---

## Overview

All list endpoints must support the following query parameters:

| Parameter    | Type          | Default       | Description                              |
|--------------|---------------|---------------|------------------------------------------|
| `page`       | int           | 1             | The current page number (1-indexed)      |
| `paging`     | int           | 10            | Number of items per page                 |
| `search`     | string \| null | null          | Search text to filter results            |
| `sort_by`    | string        | "created_at"  | Field name to sort by                    |
| `sort_order` | string        | "desc"        | Sort order: "asc" or "desc"              |

---

## Response Format

All paginated endpoints return the following structure:

```json
{
  "status": "success",
  "data": [...],
  "meta": {
    "current_page": 1,
    "next_page": 2,
    "prev_page": 1,
    "total_pages": 5,
    "total_count": 48
  }
}
```

---

## Architecture Flow

The pagination logic flows through 3 layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                        API ROUTE LAYER                          │
│  - Receives: page, paging, search, sort_by, sort_order         │
│  - Converts: page/paging → skip/limit                          │
│  - Calls: service.get_all() and service.count()                │
│  - Returns: DataResponseAPI with PageInfo meta                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SERVICE LAYER                             │
│  - Receives: skip, limit, search, sort_by, sort_order          │
│  - Delegates: to repository methods                            │
│  - Transforms: models → response schemas                        │
│  - Methods: get_all(), count()                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      REPOSITORY LAYER                           │
│  - Receives: db, skip, limit, search, sort_by, sort_order      │
│  - Builds: SQLAlchemy query with filters and sorting           │
│  - Methods: get_all(), count(), _apply_search_filter(),        │
│             _apply_sorting()                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Guide

### Step 1: Repository Layer

Create helper methods for search and sort, then use them in `get_all()` and `count()`.

```python
"""Example repository with pagination support."""

from typing import Literal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.your_module.models.your_model import YourModel


class YourRepository:
    """Repository for database operations."""

    def __init__(self):
        """Initialize repository."""
        pass

    def _apply_search_filter(self, query, search: str | None):
        """Apply search filter to query.
        
        Customize the fields to search based on your model.
        """
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    YourModel.name.ilike(search_pattern),
                    YourModel.description.ilike(search_pattern),
                    # Add more searchable fields as needed
                )
            )
        return query

    def _apply_sorting(
        self,
        query,
        sort_by: str = "created_at",
        sort_order: Literal["asc", "desc"] = "desc",
    ):
        """Apply sorting to query."""
        # Get the column to sort by, default to created_at
        sort_column = getattr(YourModel, sort_by, YourModel.created_at)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
        return query

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: Literal["asc", "desc"] = "desc",
    ) -> list[YourModel]:
        """Get all items with pagination, search, and sorting."""
        query = db.query(YourModel)
        query = self._apply_search_filter(query, search)
        query = self._apply_sorting(query, sort_by, sort_order)
        return query.offset(skip).limit(limit).all()

    def count(self, db: Session, search: str | None = None) -> int:
        """Count total items with optional search filter."""
        query = db.query(YourModel)
        query = self._apply_search_filter(query, search)
        return query.count()
```

---

### Step 2: Service Layer

The service layer passes parameters to the repository and transforms results.

```python
"""Example service with pagination support."""

from sqlalchemy.orm import Session

from app.your_module.repositories.your_repository import YourRepository
from app.your_module.schemas.your_schema import YourResponse


class YourService:
    """Service for business operations."""

    def __init__(self):
        """Initialize service."""
        self.repository = YourRepository()

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> list[YourResponse]:
        """Get all items with pagination, search, and sorting."""
        items = self.repository.get_all(
            db,
            skip=skip,
            limit=limit,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return [YourResponse.model_validate(item) for item in items]

    def count(self, db: Session, search: str | None = None) -> int:
        """Count total items with optional search filter."""
        return self.repository.count(db, search=search)
```

---

### Step 3: API Route Layer

The route layer receives client parameters (`page`, `paging`) and converts them to internal parameters (`skip`, `limit`).

```python
"""Example route with pagination support."""

from fastapi import APIRouter

from app.common.db import SessionDB
from app.common.schemas import DataResponseAPI, PageInfo
from app.your_module.services.your_service import YourService

router = APIRouter(prefix="/your-items", tags=["Your Items"])

your_service = YourService()


@router.get("", response_model=dict)
async def get_items(
    page: int = 1,
    paging: int = 10,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: SessionDB = None,
):
    """Get all items with pagination, search, and sorting."""
    # Call service with converted pagination params
    items = your_service.get_all(
        db,
        skip=(page - 1) * paging,  # Convert page to skip
        limit=paging,               # paging = limit
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    
    # Get total count for pagination meta (must respect search filter!)
    total_count = your_service.count(db, search=search)
    
    # Create page info with correct total_count
    page_info = PageInfo.create_page_info(
        current_page=page,
        page_size=paging,
        total_count=total_count,
    )
    
    return DataResponseAPI.success(data=items, meta=page_info.model_dump())
```

---

## Key Points to Remember

### ✅ DO

1. **Always use `page` and `paging` in the API** - Never expose `skip`/`limit` to clients
2. **Convert page to skip**: `skip = (page - 1) * paging`
3. **Get total_count from database** - Use `service.count(db, search=search)`
4. **Pass search to count()** - The total must reflect filtered results
5. **Use `ilike()` for search** - Case-insensitive search
6. **Default sort by `created_at` desc** - Most recent items first

### ❌ DON'T

1. **Don't use `len(items)` for total_count** - This only counts current page items
2. **Don't forget to apply search filter to count()** - Will cause wrong total_pages
3. **Don't hardcode searchable fields** - Customize `_apply_search_filter()` per model

---

## PageInfo Schema Reference

Located at: `app/common/schemas/page_info.py`

```python
class PageInfo(BaseModel):
    """Pagination information model."""

    current_page: int   # Current page number
    next_page: int      # Next page number (same as current if on last page)
    prev_page: int      # Previous page number (1 if on first page)
    total_pages: int    # Total number of pages
    total_count: int    # Total number of items matching the query

    @staticmethod
    def create_page_info(
        current_page: int = 1,
        page_size: int = 10,
        total_count: int = 0
    ) -> "PageInfo":
        """Create a PageInfo instance for pagination."""
        total_pages = (total_count + page_size - 1) // page_size or 1
        return PageInfo(
            current_page=current_page,
            total_pages=total_pages,
            total_count=total_count,
        )
```

---

## Example API Calls

```bash
# Get first page with default settings
GET /api/v1/users

# Get page 2 with 20 items per page
GET /api/v1/users?page=2&paging=20

# Search for "john"
GET /api/v1/users?search=john

# Sort by email ascending
GET /api/v1/users?sort_by=email&sort_order=asc

# Combined: search + sort + pagination
GET /api/v1/users?page=1&paging=10&search=admin&sort_by=created_at&sort_order=desc
```

---

## Checklist for New Endpoints

When creating a new list endpoint, ensure:

- [ ] Route accepts: `page`, `paging`, `search`, `sort_by`, `sort_order`
- [ ] Route converts `page`/`paging` to `skip`/`limit`
- [ ] Service has `get_all()` with all pagination params
- [ ] Service has `count()` method with search filter
- [ ] Repository has `_apply_search_filter()` with relevant fields
- [ ] Repository has `_apply_sorting()` method
- [ ] Repository `get_all()` uses both filter and sorting
- [ ] Repository `count()` uses search filter
- [ ] Route calls `service.count(db, search=search)` for `total_count`
- [ ] Route uses `PageInfo.create_page_info()` for meta
