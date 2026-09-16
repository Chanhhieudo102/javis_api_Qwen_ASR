# API Endpoint Development Guidelines

This document outlines the process for creating and modifying API endpoints in this project.

## Important Rule

**Every time you create or modify an API endpoint, you MUST also create or update the corresponding unit tests.**

## Creating a New Endpoint

### 1. Define the Schema (if needed)

Location: `app/<module>/schemas/<schema_name>.py`

```python
from pydantic import BaseModel

class MyCreate(BaseModel):
    """Schema for creating a resource."""
    field1: str
    field2: int | None = None

class MyResponse(BaseModel):
    """Response schema."""
    id: uuid.UUID
    field1: str
    field2: int | None

    model_config = {"from_attributes": True}
```

**Don't forget to export in `__init__.py`:**
```python
from app.<module>.schemas.<schema_name> import MyCreate, MyResponse

__all__ = ["MyCreate", "MyResponse", ...]
```

### 2. Add Service Method

Location: `app/<module>/services/<service_name>.py`

```python
def create_resource(self, db: Session, data: MyCreate) -> MyModel:
    """Create a new resource."""
    resource = MyModel(
        id=uuid.uuid4(),
        field1=data.field1,
        field2=data.field2,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    resource = self.repository.create(db, resource)
    db.commit()
    return resource
```

### 3. Add API Route

Location: `app/<module>/api/v1/<routes_name>.py`

```python
@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new resource",
    description="Create a new resource. Requires owner role.",
)
def create_resource(
    data: MyCreate,
    db: SessionDB = None,
    current_user: User = Depends(is_owner),
):
    """Create a new resource."""
    resource = service.create_resource(db, data)
    return DataResponseAPI.success_without_meta(data=MyResponse.model_validate(resource))
```

### 4. Create/Update Unit Tests ⚠️ REQUIRED

Location: `tests/test_<module>.py`

```python
def test_create_resource_success(client, auth_headers, test_data):
    """Test successful resource creation."""
    response = client.post(
        "/api/v1/<module>",
        json={
            "field1": "value1",
            "field2": 123,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["field1"] == "value1"


def test_create_resource_not_found(client, auth_headers):
    """Test creating resource with invalid data."""
    fake_id = uuid.uuid4()
    response = client.post(
        "/api/v1/<module>",
        json={
            "related_id": str(fake_id),
        },
        headers=auth_headers,
    )
    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "failure"
```

## Unit Test Structure

### Required Fixtures

```python
@pytest.fixture
def auth_token(client):
    """Get authentication token by logging in."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]

@pytest.fixture
def auth_headers(auth_token):
    """Get authorization headers with token."""
    return {"Authorization": f"Bearer {auth_token}"}

@pytest.fixture
def test_resource_data(client, auth_headers):
    """Create a test resource and return its data."""
    response = client.post(
        "/api/v1/<module>",
        json={"field1": "test"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()["data"]
```

### Test Categories

Each endpoint should have tests covering:

1. **Success cases** - Happy path with valid data
2. **Not found cases** - Invalid/missing resource IDs
3. **Validation errors** - Invalid request body
4. **Authorization errors** - Missing or invalid token
5. **Edge cases** - Boundary conditions, null values, etc.

### Running Tests

```bash
# Run all tests
docker compose exec app pytest tests/test_<module>.py -v

# Run specific test
docker compose exec app pytest tests/test_<module>.py::test_name -v
```

## Checklist

Before committing, ensure:

- [ ] Schema created/updated
- [ ] Schema exported in `__init__.py`
- [ ] Service method created/updated
- [ ] Route created/updated
- [ ] **Unit tests created/updated** ⚠️
- [ ] Tests pass: `docker compose exec app pytest tests/test_<module>.py -v`
- [ ] Linting passes: pre-commit hooks
