# Kiến Trúc LangGraph Cho Dự Án Javis ASR (Python 3.11)

Tài liệu này hướng dẫn chi tiết về việc ứng dụng **LangGraph** vào hệ thống backend FastAPI theo đúng chuẩn đặc tả kiến trúc tại [`agent_graph.md`](file:///d:/VJ/Encode_API_Qwen/agent_graph.md). Hệ thống bổ sung năng lực AI Agent để phân tích, biên tập văn bản ASR (chỉnh sửa dấu câu, tóm tắt cuộc họp và trích xuất danh sách hành động).

---

## 📑 Mục lục

1. [Tổng Quan Kiến Trúc](#1-tổng-quan-kiến-trúc)
2. [Cấu Trúc Thư Mục](#2-cấu-trúc-thư-mục)
3. [Chi Tiết Các Thành Phần](#3-chi-tiết-các-thành-phần)
   - [Tầng Agent dùng chung (`app/agent`)](#31-tầng-agent-dùng-chung-appagent)
   - [Feature Graph: Transcript Analysis (`app/voice2text/graphs/transcript_analysis`)](#32-feature-graph-transcript-analysis)
   - [Tầng Service & API Route](#33-tầng-service--api-route)
4. [Cơ Chế Dự Phòng & Xử Lý Lỗi (Failover)](#4-cơ-chế-dự-phòng--xử-lý-lỗi-failover)
5. [Yêu Cầu Môi Trường & Cài Đặt (Python 3.11)](#5-yêu-cầu-môi-trường--cài-đặt-python-311)
6. [Hướng Dẫn Kiểm Thử (Unit Tests)](#6-hướng-dẫn-kiểm-thử-unit-tests)
7. [Hướng Dẫn Sử Dụng API](#7-hướng-dẫn-sử-dụng-api)
8. [Bảng Tuân Thủ Chuẩn Kiến Trúc (`agent_graph.md`)](#8-bảng-tuân-thủ-chuẩn-kiến-trúc-agent_graphmd)

---

## 1. Tổng Quan Kiến Trúc

Hệ thống tuân thủ mô hình **Clean Architecture + Strict Layering**:
- **Không Checkpointer (Stateless)**: Đồ thị không lưu trữ trạng thái giữa các request, được biên dịch một lần duy nhất lúc import (`registry.py`).
- **Phân tách tầng chặt chẽ**: Graph Nodes **tuyệt đối không** import từ `services/`. Toàn bộ prompt, parser và logic nghiệp vụ thuần túy nằm tại `helpers.py`.
- **Single Model Provider**: Mọi model LLM đều được quản lý tập trung qua `app/agent/models.py`.

```mermaid
flowchart TD
    Client([HTTP Client / Postman]) -->|POST /api/v2/transcript/analyze| Router[API Route: routes.py]
    Router --> Service[TranscriptAnalysisGraphService]
    Service -->|traced_run_name| GraphSingleton[TRANSCRIPT_ANALYSIS_GRAPH]
    
    subgraph LangGraph Pipeline [Feature Graph: transcript_analysis]
        InputSchema[TranscriptAnalysisInput] --> Node1[Clean & Punctuate Node]
        Node1 -->|Intermediate State| Node2[Summarize & Action Items Node]
        Node2 --> OutputSchema[TranscriptAnalysisOutput]
    end
    
    GraphSingleton --> LangGraph Pipeline
    
    subgraph Common Agent Layer [app/agent]
        Node1 -.->|ainvoke| RunnableModel[RunnableChatModel]
        Node2 -.->|ainvoke| RunnableModel
        RunnableModel --> Primary[Primary ChatModel: OpenAI / Azure]
        Primary -.->|On Failure| Fallback[Fallback ChatModel]
    end
    
    OutputSchema --> Router
    Router --> Response([JSON Response])
```

---

## 2. Cấu Trúc Thư Mục

```
javis-api-qwen3-hf/
├── app/
│   ├── agent/                                    # Tầng Agent dùng chung (Single Provider)
│   │   ├── clients/
│   │   │   ├── chat_model.py                     # ChatModel Protocol
│   │   │   ├── llm_client.py                     # Factory khởi tạo ChatOpenAI
│   │   │   └── runnable_chat_model.py            # Wrapper failover, logging & error wrapping
│   │   ├── constants/
│   │   │   ├── graph_constants.py                # Keys cấu hình (configurable, tags, metadata)
│   │   │   └── model_constants.py                # Hằng số thông điệp log failover
│   │   ├── enums/
│   │   │   └── model_enums.py                    # Enum ModelPurpose (TRANSCRIPT_ANALYSIS, ...)
│   │   ├── schemas/
│   │   │   └── model_profile.py                  # Pydantic schema ModelProfile
│   │   ├── utils/
│   │   │   ├── chat_request.py                   # Tiện ích xây dựng danh sách BaseMessage
│   │   │   └── run_context.py                    # Xây dựng traced run name và config
│   │   └── models.py                             # Single provider module quản lý model profiles
│   │
│   ├── voice2text/
│   │   ├── graphs/
│   │   │   └── transcript_analysis/              # Feature Graph: Phân tích transcript
│   │   │       ├── builder.py                    # Khởi tạo StateGraph & liên kết nodes
│   │   │       ├── helpers.py                    # Prompt builders & output parsers (pure functions)
│   │   │       ├── nodes.py                      # Class-based nodes (CleanPunctuate, Summarize)
│   │   │       ├── registry.py                   # Compiled graph singleton
│   │   │       └── state.py                      # Schema Input, State, Output (TypedDict)
│   │   ├── constants/
│   │   │   └── transcript_analysis_graph_constants.py
│   │   ├── enums/
│   │   │   └── transcript_analysis_graph_enums.py
│   │   ├── schemas/
│   │   │   └── transcript_analysis_schemas.py    # Request / Response schemas Pydantic
│   │   ├── services/
│   │   │   └── transcript_analysis_graph_service.py # Service gọi Graph & sinh run context
│   │   └── api/v2/
│   │       └── routes.py                         # Endpoint POST /transcript/analyze
│   │
│   └── common/
│       ├── constants/
│       │   └── error_constants.py                # Thêm ErrorConstants.Agent.MODEL_REQUEST_FAILED
│       └── resources/errors/                     # Mã lỗi i18n ERR.AGT0101
│           ├── error_en.yml
│           ├── error_ja.yml
│           └── error_vi.yml
│
├── tests/
│   └── test_agent_graphs.py                      # 7 Unit tests độc lập, không phụ thuộc mạng
└── pyproject.toml                                # Cập nhật langgraph, langchain-core, langchain-openai
```

---

## 3. Chi Tiết Các Thành Phần

### 3.1 Tầng Agent dùng chung (`app/agent`)

- **Protocol `ChatModel`**: Quy định interface chuẩn `ainvoke(messages, config=None) -> AIMessage`.
- **`RunnableChatModel`**:
  - Dùng `primary_model.with_fallbacks([fallback_model])`.
  - Tự động bắt sự kiện failover và ghi warning log:
    ```
    Failover occurred for purpose 'transcript_analysis'. Primary model 'gpt-4o' failed, fallback model 'gpt-4o-mini' responded.
    ```
  - Nếu tất cả các model trong chuỗi thất bại, đóng gói ngoại lệ thành:
    `InternalServerException(ErrorConstants.Agent.MODEL_REQUEST_FAILED)` (`ERR.AGT0101`).
- **`models.py`**: Điểm duy nhất trong toàn hệ thống được khởi tạo Chat Model và gán profile fallback (`MODEL_PROFILES`).
- **`run_context.py`**: Sinh `traced_run_name` chuẩn định dạng: `<graph_name>_<request_id>_<timestamp_utc>`.

---

### 3.2 Feature Graph: Transcript Analysis

Pipeline gồm 2 bước xử lý tuần tự:
1. **`clean_punctuate`**: Tiếp nhận văn bản thô từ ASR (thiếu dấu câu, viết hoa lộn xộn, từ đệm), chuẩn hóa thành văn bản mạch lạc.
2. **`summarize_actions`**: Nhận văn bản đã làm sạch, tóm tắt nội dung chính và trích xuất danh sách công việc cần làm (`action_items`) theo chuẩn JSON.

#### Phân tách Schema rõ ràng (`state.py`):
- `TranscriptAnalysisInput`: `raw_transcript`, `language`.
- `TranscriptAnalysisState`: Chứa thêm các trường tính toán trung gian (`cleaned_transcript`).
- `TranscriptAnalysisOutput`: Chỉ trả về: `cleaned_transcript`, `summary`, `action_items`. Các trường đầu vào không bị rò rỉ ra output.

#### Triển khai Node dạng Class (`nodes.py`):
```python
class TranscriptAnalysisCleanPunctuateNode:
    def __init__(self, model: ChatModel, system_prompt: str) -> None:
        self.model = model
        self.system_prompt = system_prompt

    async def work(self, state: TranscriptAnalysisState, config: RunnableConfig) -> dict:
        # Nhận state qua tham số, không lưu request state vào self!
        ...
```

#### Biên dịch Singleton (`registry.py`):
```python
# Graph được compile 1 lần duy nhất tại import-time, hoàn toàn stateless
TRANSCRIPT_ANALYSIS_GRAPH: CompiledStateGraph = build()
```

---

### 3.3 Tầng Service & API Route

- **`TranscriptAnalysisGraphService`**: 
  - Khởi tạo `run_id` duy nhất (UUID v4).
  - Chuẩn bị cấu hình tracing qua `run_config(run_name=traced_run_name(...))`.
  - Gọi graph: `await self._graph.ainvoke(input_data, config=cfg)`.
- **API Endpoint**: `POST /api/v2/transcript/analyze`
  - Nhận JSON request `TranscriptAnalysisRequest`.
  - Trả về JSON `TranscriptAnalysisResponse`.

---

## 4. Cơ Chế Dự Phòng & Xử Lý Lỗi (Failover)

| Tình huống | Hành vi của hệ thống | Log / Mã lỗi trả về |
| :--- | :--- | :--- |
| **Model chính thành công** | Trả kết quả bình thường | Response 200 OK |
| **Model chính lỗi (Timeout, 5xx...)** | Kích hoạt Fallback model ngay lập tức | Warning: `Failover occurred for purpose '...'` |
| **Tất cả model đều lỗi** | Chuỗi cạn kiệt, bọc lại lỗi có kiểu | `500 Internal Server Error`<br>Mã lỗi: `ERR.AGT0101` (`agent_model_request_failed`) |

Mã lỗi `ERR.AGT0101` được định nghĩa đa ngôn ngữ:
- **Tiếng Anh**: *"AI model request failed. All fallback models in the chain were exhausted."*
- **Tiếng Nhật**: *"AIモデルのリクエストに失敗しました。すべての代替モデルが枯渇しました。"*
- **Tiếng Việt**: *"Yêu cầu mô hình AI thất bại. Tất cả mô hình dự phòng trong chuỗi đều đã hết."*

---

## 5. Yêu Cầu Môi Trường & Cài Đặt (Python 3.11)

### Yêu cầu
- Python: **3.11.x** (Bắt buộc theo chuẩn dự án)
- Quản lý gói: `pip` hoặc `poetry`

### Cài đặt môi trường
1. Di chuyển vào thư mục backend:
   ```powershell
   cd javis-api-qwen3-hf
   ```
2. Kích hoạt môi trường ảo Python 3.11:
   ```powershell
   # Trên Windows PowerShell:
   .\.venv\Scripts\Activate.ps1
   ```
3. Cài đặt các thư viện cần thiết:
   ```bash
   pip install langgraph langchain-core langchain-openai pytest pytest-asyncio ruff
   ```

---

## 6. Hướng Dẫn Kiểm Thử (Unit Tests)

Tất cả unit test được viết trong [`tests/test_agent_graphs.py`](file:///d:/VJ/Encode_API_Qwen/javis-api-qwen3-hf/tests/test_agent_graphs.py) sử dụng `GenericFakeChatModel` từ `langchain_core`. **Không gọi mạng, không cần OpenAI API key, tốc độ chạy chỉ dưới 1 giây.**

### Chạy kiểm thử:
```powershell
cd javis-api-qwen3-hf
.\.venv\Scripts\pytest.exe tests/test_agent_graphs.py -v
```

### Kết quả kiểm thử:
```
tests/test_agent_graphs.py::test_failover_when_primary_fails PASSED           [ 14%]
tests/test_agent_graphs.py::test_failover_logs_warning PASSED                 [ 28%]
tests/test_agent_graphs.py::test_exhausted_chain_raises_typed_error PASSED      [ 42%]
tests/test_agent_graphs.py::test_graph_statelessness PASSED                   [ 57%]
tests/test_agent_graphs.py::test_output_schema_filters_scratch_fields PASSED [ 71%]
tests/test_agent_graphs.py::test_node_instances_hold_config_not_request_state PASSED [ 85%]
tests/test_agent_graphs.py::test_traced_run_name_format PASSED                [100%]

======================== 7 passed in 0.65s =========================
```

### Kiểm tra Code Style với Ruff:
```powershell
.\.venv\Scripts\ruff.exe check --config pyproject.toml app/agent app/voice2text/graphs tests/test_agent_graphs.py
# Kết quả: All checks passed!
```

---

## 7. Hướng Dẫn Sử Dụng API

### Endpoint: `POST /api/v2/transcript/analyze`

#### 1. Request Body:
```json
{
  "raw_transcript": "hôm nay chúng ta họp về tiến độ dự án anh nam sẽ hoàn thành api vào thứ sáu còn chị hoa sẽ kiểm thử trước thứ hai tuần tới",
  "language": "Vietnamese"
}
```

#### 2. Lệnh gọi qua cURL:
```bash
curl -X POST "http://localhost:8000/api/v2/transcript/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_transcript": "hôm nay chúng ta họp về tiến độ dự án anh nam sẽ hoàn thành api vào thứ sáu còn chị hoa sẽ kiểm thử trước thứ hai tuần tới",
    "language": "Vietnamese"
  }'
```

#### 3. Response Body (200 OK):
```json
{
  "cleaned_transcript": "Hôm nay chúng ta họp về tiến độ dự án. Anh Nam sẽ hoàn thành API vào thứ Sáu, còn chị Hoa sẽ kiểm thử trước thứ Hai tuần tới.",
  "summary": "Cuộc họp thống nhất tiến độ phát triển và kiểm thử API của dự án.",
  "action_items": [
    "Anh Nam hoàn thành API vào thứ Sáu",
    "Chị Hoa kiểm thử trước thứ Hai tuần tới"
  ]
}
```

---

## 8. Bảng Tuân Thủ Chuẩn Kiến Trúc (`agent_graph.md`)

| Quy chuẩn trong `agent_graph.md` | Trạng thái | Minh chứng thực hiện |
| :--- | :---: | :--- |
| **1. Single Provider Module** | ✅ Đạt | `models.py` chỉ quản lý model & fallback, không chứa graph logic. |
| **2. Class-based Nodes** | ✅ Đạt | Các node đều là class có `__call__`/`work`, `self` chỉ chứa config, không chứa request state. |
| **3. Compile Once at Import** | ✅ Đạt | `TRANSCRIPT_ANALYSIS_GRAPH` được compile tại `registry.py` dưới dạng singleton. |
| **4. Strict Layering** | ✅ Đạt | Không có bất kỳ node nào import từ `services/`. Nghiệp vụ thuần nằm ở `helpers.py`. |
| **5. Graph Isolation** | ✅ Đạt | Không cross-import giữa các graphs. |
| **6. Unique Node Names** | ✅ Đạt | Định nghĩa qua enum `TranscriptAnalysisNodeName` (`clean_punctuate`, `summarize_actions`). |
| **7. Pre-generated Traced Run ID** | ✅ Đạt | Sinh UUID v4 qua `traced_run_name` trước khi gọi `ainvoke`. |
| **8. Separate State Schehai** | ✅ Đạt | Phân tách `*Input`, `*State`, `*Output` TypedDicts trong `state.py`. |
| **9. Statelessness (No Checkpointer)** | ✅ Đạt | Không sử dụng `MemorySaver` hay checkpointer, không tích lũy state qua các lượt gọi. |
| **10. Unit Tests Isolation** | ✅ Đạt | Sử dụng `GenericFakeChatModel`, không gọi network/database, chạy độc lập. |
| **11. Môi trường Python 3.11** | ✅ Đạt | Toàn bộ package và môi trường virtualenv chạy trên Python 3.11.9. |
