## Feature Request Lifecycle

The typical flow for handling a request in a feature module is:

1. **Router (API Layer)**  
   - Receives the HTTP request from the client.
   - Parses and validates input using Pydantic schemas.
   - Injects the database session (`SessionDB`) via dependency injection.
   - Calls the appropriate service function or class method, passing the `db` session.

2. **Service Layer**  
   - Receives the database session from the router.
   - Contains business logic and core operations.
   - Processes the request, interacts with repositories, models, and utilities as needed.
   - Passes the database session to repository methods when needed.
   - Returns the result or response data to the router.

3. **Repository Layer (if needed)**  
   - Receives the database session as a parameter for each method.
   - Handles database queries and persistence using the provided session.
   - Fetches or saves data as requested by the service.

4. **Response**  
   - The router formats and returns the response to the client.

**Database Session Flow:**  
`Route (injects SessionDB) → Service (receives db, passes to repo) → Repository (receives db, executes queries)`

---

## Feature Module Folder Structure

Each feature under `app/<feature>/` is organized into several main folders. Here’s what each part does, with examples from the `chatbot` feature:

- **api/**  
  Contains API route definitions for the feature (e.g., REST endpoints, versioning).  
  *Example:*  
  - `api/v1/routes.py`: FastAPI routes for version 1 of the chatbot API.
    ```python
    from chatbot.services.impl.roof_service_impl import RoofServiceImpl
    from common.db.session import SessionDB
    from fastapi import APIRouter

    router = APIRouter(tags=["Chatbot"], prefix="/roof")
    
    # Initialize service once outside route functions
    roof_service = RoofServiceImpl()

    # Example endpoint for solar dimension calculation
    @router.post("/draw")
    async def get_solar_dimension(request: RoofFormRequest, db: SessionDB = None):
        # SessionDB is injected via dependency injection
        # Pass db session to service method
        return await roof_service.get_solar_dimension(db, request)
    
    @router.get("/conversations")
    async def get_conversations(
        user_id: uuid.UUID = Query(..., description="User Id"),
        page: int = Query(1, ge=1, description="Page number"),
        paging: int = Query(10, ge=1, description="Items per page"),
        db: SessionDB = None,
    ):
        # Service receives db and passes it to repository
        return roof_service.get_conversations(db, user_id, page, paging)
    ```
  **Key Points:**
  - Service is instantiated **once** outside route functions for better performance.
  - `SessionDB` is injected as a route parameter using FastAPI's dependency injection.
  - Database session is passed from route → service → repository for each request.
  - This pattern ensures proper session management and transaction handling.

- **configs/**  
  Configuration files and settings specific to the feature.  
  *Example:*  
  - `configs/setting.py`: Defines environment variables, file paths, and other settings using Pydantic.  
    ```python
    class Settings(BaseSettings):
        BASE_TEMPLATE_URL: str = ""
        SERVICE_URL: str = ""
        panel_data_path: str = str(DATA_DIR / "panel_data.json")
        template_path: str = str(DATA_DIR / "template.xlsx")
        default_image: str = str(DATA_DIR / "default_image.png")
        labels: list[str] = ["屋根面2", "屋根面1"]

        class Config:
            env_file = f".env"
            env_file_encoding = "utf-8"
            extra = "ignore"
    settings = Settings()
    ```
  This pattern allows each feature to manage its own configuration, environment variables, and resource paths in a centralized, maintainable way.

- **constants/**  
  Constant values, prompts, and mappings used throughout the feature.  
  *Example:*  
  - `constants/prompt.py`: Contains reusable prompt templates and constant strings for chatbot operations.  
    ```python
    class ChatbotPrompts:
        INTENT_CLASSIFIER_SYSTEM = """# Role: You are an expert in analyzing and classifying contexts
        into categories.
        # Objective: Your task is to analyze the context, and decide which category the context belongs to
        # based on its meaning.
        # Instructions:
        - You are given a context of a conversation history and a user's latest question.
        - Your task is to classify the context into one of the following categories:
            1. roof: ...
            2. other: ...
        # Note:
        - Prefer the user's messages (especially user's latest message) than the assistant's messages.
        - Only provide your answer, no other text or comment.
        """
    ```
  This pattern centralizes important constant values and templates, making them easy to reuse and maintain.

- **enums/**  
  Enumerations for types, categories, error codes, etc.  
  *Example:*  
  - `enums/roofs.py`: Defines enums for roof shapes, positions, and overlap axes.  
    ```python
    from enum import StrEnum

    class ERoofShapeType(StrEnum):
        RECTANGLE = "rectangle"
        TRIANGLE = "triangle"
        TRAPEZOID = "trapezoid"
        UNKNOWN = "unknown"

    class ERoofPosition(StrEnum):
        TOP = "top"
        BOTTOM = "bottom"
        LEFT = "left"
        RIGHT = "right"
        CENTER = "center"

    class EOverlapAxis(StrEnum):
        WIDTH = "width"
        HEIGHT = "height"
        UNKNOWN = "unknown"
    ```
  This pattern provides clear, type-safe definitions for categorical values used throughout the feature.

- **models/**  
  Database models and ORM classes.  
  *Example:*  
    ```python
    class Conversation(SnakeBase, BaseModelMixin):
        id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
        user_id = Column(UUID(as_uuid=True), nullable=False)
        name = Column(String, nullable=True)

        histories = relationship(
            "History",
            back_populates="conversation",
            cascade="all, delete-orphan",
        )
    ```
  This pattern defines the structure of data stored in the database and relationships between entities.

  **Voice2Text note:** the `conversations` table now includes a `type_conversation` column (`voice` for any audio-created conversation; `chatbot` for empty conversations created via `POST /api/v1/voice2text/conversation`). Responses containing `ConversationSchema` or `CreateConversationResponse` also surface this field.

- **repositories/**  
  Data access layer, handles database queries and persistence.  
  *Example:*  
    ```python
    class RoofRepository:
        def __init__(self):
            """Repository for managing roof data."""
            pass

        def create_conversation(
            self,
            db,
            payload_conversation: ConversationCreateRequest,
            payload_history: HistoryCreateRequest,
        ) -> HistoryResponse:
            """Create a new conversation and its initial history entry.
            
            Args:
                db: Database session passed from service layer.
                payload_conversation: Conversation creation data.
                payload_history: History creation data.
            
            Returns:
                HistoryResponse: Created history response.
            """
            conversation_id = payload_conversation.conversation_id or uuid.uuid4()
            exist_conversation = db.query(Conversation).filter_by(id=conversation_id).first()
            
            if not exist_conversation:
                conversation = Conversation(
                    id=conversation_id,
                    user_id=payload_conversation.user_id,
                    name=payload_conversation.conversation_name,
                )
                db.add(conversation)
                # ...additional logic...
            
            db.commit()
            return history_response

        def get_conversations(self, db, user_id: uuid.UUID, page: int, paging: int):
            """Fetch all conversations for a user with pagination.
            
            Args:
                db: Database session passed from service layer.
                user_id: The ID of the user.
                page: The page number.
                paging: The number of items per page.
            """
            query = db.query(Conversation).filter(Conversation.user_id == user_id)
            total_count = query.count()
            items = query.offset((page - 1) * paging).limit(paging).all()
            # ...return formatted response...
            
        def get_conversation_by_id(self, db, conversation_id: uuid.UUID) -> Conversation | None:
            """Get conversation by ID.
            
            Args:
                db: Database session passed from service layer.
                conversation_id: The conversation ID to check.
            
            Returns:
                Conversation | None: Conversation object if exists, otherwise None.
            """
            return db.query(Conversation).filter(Conversation.id == conversation_id).first()
    ```
  **Key Points:**
  - Repository **does not** store `db` as an instance variable.
  - Each method receives `db` as a parameter from the service layer.
  - This pattern ensures thread-safety and proper session management per request.
  - Database operations are centralized, making them easier to maintain, test, and update.

- **resources/**  
  Static files, templates, or other resources required by the feature.  
  *Example:*  
  - `resources/`: (May contain images, templates, or other static assets.)

- **schemas/**  
  Pydantic models for request/response validation and data structures.  
  *Example:*  
  - `schemas/roof_shape.py`: Defines the data structure for roof shapes used in API requests and responses.  
    ```python
    from typing import List, Optional
    from pydantic import BaseModel

    class RoofShape(BaseModel):
        id: int
        shape_type: str
        width: Optional[float] = None
        height: Optional[float] = None
        angle: Optional[float] = None
        area: Optional[float] = None
        direction: Optional[int] = None
        limit_line: Optional[int] = None
        limit_line_width: List[int] = []
        limit_line_height: List[int] = []
    ```
  This pattern ensures data consistency and validation for API inputs and outputs using Pydantic models.

- **services/**  
  Business logic, service classes, and core operations for the feature.  
  You can define services using either class-based or function-based patterns.

  *Example (class-based):*  
  - `services/roof_service.py`: Abstract base class defining the interface for roof-related operations.
    ```python
    from abc import ABC, abstractmethod
    from sqlalchemy.orm import Session
    
    class RoofService(ABC):
        def __init__(self):
            """Service for managing roof-related operations."""
            pass
        
        @abstractmethod
        def get_roof_info(self, db: Session, user_id: uuid.UUID, conversation_id: uuid.UUID, file):
            """Fetch roof information.
            
            Args:
                db (Session): Database session from route layer.
                user_id (uuid.UUID): The ID of the user.
                conversation_id (uuid.UUID): The ID of the conversation.
                file: The uploaded file.
            """
            pass
        
        @abstractmethod
        def get_conversations(self, db: Session, user_id: uuid.UUID, page: int, paging: int):
            """Fetch all conversations.
            
            Args:
                db (Session): Database session from route layer.
                user_id (uuid.UUID): The ID of the user.
                page (int): The page number.
                paging (int): The number of items per page.
            """
            pass
    ```
  - `services/impl/roof_service_impl.py`: Implements the business logic for roof operations.
    ```python
    from sqlalchemy.orm import Session
    
    class RoofServiceImpl(RoofService):
        def __init__(self):
            """Service for managing roof-related operations."""
            super().__init__()
            self.repo = RoofRepository()  # Repository initialized without db
        
        async def get_roof_info(self, db: Session, user_id, conversation_id, file):
            """Fetch roof information.
            
            Args:
                db (Session): Database session passed from route.
                user_id: The ID of the user.
                conversation_id: The ID of the conversation.
                file: The uploaded file.
            """
            # Validate and process file
            FileUtils.validate_file(file)
            file_meta = await FileUtils.upload_file(file)
            roof_info = await RoofProcessor.get_roof_info(file)
            
            # Pass db to repository methods
            history_response = self.repo.create_conversation(
                db=db,  # Pass db session to repository
                payload_conversation=ConversationCreateRequest(...),
                payload_history=HistoryCreateRequest(...),
            )
            
            return DataResponseAPI.success_without_meta(chat_response)
        
        def get_conversations(self, db: Session, user_id: uuid.UUID, page: int = 1, paging: int = 10):
            """Fetch all conversations.
            
            Args:
                db (Session): Database session passed from route.
                user_id: The ID of the user.
                page: The page number.
                paging: The number of items per page.
            """
            # Pass db to repository
            return self.repo.get_conversations(db, user_id, page, paging)
    ```

  *Example (function-based):*  
  - `services/roof_service.py`:  
    ```python
    from sqlalchemy.orm import Session
    
    async def get_roof_info(db: Session, user_id, conversation_id, file):
        """Fetch roof information.
        
        Args:
            db (Session): Database session passed from route.
            user_id: The ID of the user.
            conversation_id: The ID of the conversation.
            file: The uploaded file.
        """
        # Validate and process file, fetch roof info, save history, return response
        repo = RoofRepository()
        history = repo.create_conversation(db, ...)
        ...
    ```
  **Key Points:**
  - Service **does not** store `db` as an instance variable.
  - Service is instantiated **once** (typically in routes) for better performance.
  - Each service method receives `db` as the first parameter after `self`.
  - Service passes `db` to repository methods when database operations are needed.
  - This pattern allows you to choose between class-based or function-based service definitions, depending on the complexity and needs of your feature.
  
- **utils/**  
  Utility functions and helpers for complex processing or calculations.  
  *Example:*  
  - `utils/triangle.py`: Contains geometric functions for triangle rotation and positioning.  
    ```python
    def rotate_triangle_to_direction(vertices: list[tuple[float, float]], direction: str):
        # Rotates triangle vertices so the apex points to the specified direction
        ...
    ```
  You can define additional folders for specialized logic, such as:
  - **llm/**: Large language model integration and processing.
  - **agent/**: Agent logic and orchestration.
  - **other custom folders**: For any complex or reusable processing needed by your feature.

  This pattern keeps advanced logic organized and easy to maintain, separating utility code from business logic.

---

## Database Session Management Pattern

The application follows a **dependency injection pattern** for database session management, ensuring thread-safety, proper transaction handling, and clean separation of concerns.

### SessionDB Flow: Route → Service → Repository

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Route Layer (API)                                        │
│    - FastAPI injects SessionDB via dependency injection     │
│    - Service instantiated ONCE outside route functions      │
│    - Pass db to service method                              │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Service Layer                                            │
│    - Receives db as method parameter                        │
│    - Processes business logic                               │
│    - Pass db to repository methods                          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Repository Layer                                         │
│    - Receives db as method parameter                        │
│    - Executes database queries using provided session       │
│    - Returns results to service                             │
└─────────────────────────────────────────────────────────────┘
```

### Complete Example

**1. Define SessionDB (common/db/session.py):**
```python
from typing import Annotated
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session
from fastapi import Depends

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

SessionDB = Annotated[Session, Depends(get_db)]
```

**2. Route Layer (api/v1/routes.py):**
```python
from chatbot.services.impl.roof_service_impl import RoofServiceImpl
from common.db.session import SessionDB
from fastapi import APIRouter

router = APIRouter(tags=["Chatbot"], prefix="/roof")

# Service instantiated ONCE
roof_service = RoofServiceImpl()

@router.get("/conversations")
async def get_conversations(
    user_id: uuid.UUID = Query(...),
    page: int = Query(1, ge=1),
    paging: int = Query(10, ge=1),
    db: SessionDB = None,  # SessionDB injected here
):
    # Pass db to service
    return roof_service.get_conversations(db, user_id, page, paging)
```

**3. Service Layer (services/impl/roof_service_impl.py):**
```python
class RoofServiceImpl(RoofService):
    def __init__(self):
        super().__init__()
        self.repo = RoofRepository()  # No db in constructor
    
    def get_conversations(self, db: Session, user_id: uuid.UUID, page: int = 1, paging: int = 10):
        """Receive db from route, pass to repository."""
        return self.repo.get_conversations(db, user_id, page, paging)
```

**4. Repository Layer (repositories/roof_repository.py):**
```python
class RoofRepository:
    def __init__(self):
        pass  # No db stored as instance variable
    
    def get_conversations(self, db, user_id: uuid.UUID, page: int, paging: int):
        """Receive db from service, use for queries."""
        query = db.query(Conversation).filter(Conversation.user_id == user_id)
        total_count = query.count()
        items = query.offset((page - 1) * paging).limit(paging).all()
        return DataResponseAPI.success(data=items, meta=page_info)
```

### Key Benefits

✅ **Thread-Safety**: Each request gets its own database session  
✅ **Proper Transaction Handling**: Sessions are automatically committed/rolled back  
✅ **Clean Separation**: Route → Service → Repository with clear responsibilities  
✅ **Testability**: Easy to mock database sessions in unit tests  
✅ **Performance**: Service instantiated once, not per request  
✅ **Maintainability**: Centralized session management in one place

### Common Mistakes to Avoid

❌ **Don't** store `db` as an instance variable in Service or Repository  
❌ **Don't** create new service instances in route functions  
❌ **Don't** use `next(get_db())` directly in constructors  
✅ **Do** pass `db` as a method parameter through all layers  
✅ **Do** instantiate services once outside route functions  
✅ **Do** let FastAPI handle session lifecycle via dependency injection

---

**Tip:**  
When adding a new feature, follow this structure to keep code organized, maintainable, and consistent across the monorepo.