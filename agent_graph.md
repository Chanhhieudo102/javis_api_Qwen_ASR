# Hướng Dẫn Phát Triển Agent Graph

Tài liệu này mô tả quy chuẩn xây dựng các agent graph trong dự án. Một graph tuân thủ kiến trúc phân tầng tương tự như mọi module khác — route tinh gọn (thin routes), service phi trạng thái (stateless services), lỗi định kiểu (typed errors) — cùng một điểm bổ sung: package `graphs/`, bởi vì một graph đã biên dịch (compiled graph) là một dạng cấu phần (artefact) hoàn toàn mới.

Cơ chế graph dùng chung nằm tại `app/agent/`. Một graph thuộc về một tính năng cụ thể sẽ nằm trong package `graphs/` của chính tính năng đó — xem [Graph được đặt ở đâu](#graph-được-đặt-ở-đâu).

---

## Tổng quan

```
┌─────────────────────────────────────────────────────────────────┐
│                          TẦNG ROUTE                             │
│  async def, tinh gọn. Depends(require_api_key)                  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         TẦNG SERVICE                            │
│  Tạo graph input và run config, lựa chọn graph                  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                          TẦNG GRAPH                             │
│  graph.ainvoke / astream  →  kết quả phản hồi                   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         TẦNG HELPER                             │
│  Các bước nội bộ của graph: prompt, parse, duyệt, định hình dữ  │
│  liệu. Không xử lý HTTP.                                        │
└─────────────────────────────────────────────────────────────────┘
```

`route → service → graph → helpers`, chỉ theo một chiều duy nhất. Request vào, kết quả trả ra, không ghi đè hay lưu trữ bất cứ thứ gì.

> ### ⚠️ Node không bao giờ import service
>
> Mũi tên phụ thuộc dừng lại ở tầng graph. Một node mà import từ `services/` đồng nghĩa với `graph → service` — đảo ngược phân tầng kiến trúc — và đây là sai lầm dễ mắc phải nhất, vì thứ mà node cần thường *nghe có vẻ* giống như một service.
>
> Khi một node cần một chức năng nào đó, hãy đọc xem file đó thực sự làm gì. Nếu nó dựng prompt cho model, parse câu trả lời, duyệt qua tài liệu (walk document) hay định hình một giá trị (shape value), thì nó hoàn toàn không phải là một service: đó là một bước (step) thuộc về graph này. **Hãy chuyển nó vào thư mục của chính graph đó** và coi nó là một helper.
>
> ```
> app/<feature>/graphs/<graph_name>/intake.py     ← helper, chỉ duy nhất graph này gọi
> app/<feature>/utils/mapping_input.py            ← helper, các luồng khác cũng gọi
> ```
>
> Một helper được hai luồng dùng chung sẽ được đặt trong `utils/`, thuộc phạm vi chung của cả hai. Những gì còn lại trong `services/` chỉ là những thứ mà route gọi trực tiếp.

---

## Tính phi trạng thái (Statelessness) — Cam kết kiến trúc

**Graph không lưu trữ bất kỳ thứ gì.** Không dùng checkpointer, không có bảng `conversation`, không có bảng `message` và không có `thread_id`. Mỗi lượt chạy đều bắt đầu hoàn toàn từ input được truyền vào và chỉ để lại vết thực thi (step trace).

Những hệ quả của cam kết này cần được nêu rõ ràng, vì chúng rất dễ bị quên lãng khi thêm một tính năng mới:

- **Graph không có bộ nhớ (memory).** Nếu client muốn ngữ cảnh từ lượt chạy trước, client phải gửi lại ngữ cảnh đó trong request, bị giới hạn bởi một hằng số đã được định nghĩa trong request schema.
- **Không có cơ chế resume và không có `interrupt()`.** Human-in-the-loop, time travel và khôi phục khi crash (crash recovery) đều bắt buộc phải có checkpointer. Việc thêm bất kỳ tính năng nào trong số này đồng nghĩa với việc đưa checkpointer trở lại — đây là một quyết định về mặt thiết kế (design decision), chứ không đơn thuần là chi tiết triển khai.
- **Graph không giữ kết nối (hold no connections)**, do đó chúng được biên dịch (compile) một lần duy nhất khi import trong `registry.py` thay vì trong lifespan của ứng dụng.
- **Không cần viết kiểm tra quyền sở hữu (ownership check)**, vì không có tài nguyên nào được lưu trữ hay sở hữu. Nếu một tài nguyên lưu trữ được thêm lại sau này, việc kiểm tra quyền sở hữu sẽ quay trở lại cùng với nó.

```python
graph_input = build_graph_input(data)          # dữ liệu từ request, không replay dữ liệu cũ
result = await YOUR_GRAPH.ainvoke(graph_input, config)
```

---

## Graph được đặt ở đâu

**`app/agent/` chỉ chứa những thành phần mà nhiều graph có thể dùng chung.** Không có domain cụ thể của bất kỳ tính năng nào được phép can thiệp vào đây: nó không biết document, field, session hay transcript là gì.

```
app/agent/
├── models.py                   module DUY NHẤT chỉ định tên provider
├── clients/
│   ├── chat_model.py           contract ChatModel mà các nơi gọi phụ thuộc vào
│   ├── llm_client.py           một upstream thô duy nhất, không có failover
│   └── runnable_chat_model.py  contract bọc một runnable hỗ trợ fallbacks
├── constants/
│   ├── graph_constants.py      các key run-contract của LangGraph
│   └── model_constants.py
├── enums/model_enums.py        ModelPurpose
├── schemas/model_profile.py    ModelProfile
└── utils/
    ├── chat_request.py         cách một lượt hội thoại được render cho gateway
    └── run_context.py          run_config() + run_value()
```

**Graph thuộc về tính năng nào thì nằm trong tính năng đó**, tuyệt đối không nằm trong module dùng chung:

```
app/<feature>/
├── api/v3/<feature>_routes.py       tinh gọn; service singleton cấp module
├── constants/<feature>_graph_constants.py   các run-config key, run name
├── enums/<feature>_graph_enums.py           NodeName
├── services/<feature>_graph_service.py      ← chạy graph. KHÔNG nằm trong graphs/
├── utils/                                   helpers dùng chung với các luồng khác
└── graphs/
    ├── __init__.py
    ├── shared/                              các bước mà nhiều hơn một graph gọi
    └── <graph_name>/                        mỗi thư mục cho một graph
        ├── __init__.py
        ├── state.py
        ├── nodes.py
        ├── builder.py
        ├── registry.py                      singleton đã biên dịch
        └── <helper>.py                      các bước chỉ duy nhất graph này gọi
```

Bốn quy tắc duy trì cấu trúc này:

1. **Mỗi graph một thư mục con riêng biệt.** `graphs/<graph_name>/`, không bao giờ để các file trôi nổi trực tiếp trong `graphs/`. Nhờ đó, graph thứ hai sẽ nằm cạnh graph thứ nhất thay vì lồng vào nhau, và không có file nào phải đổi tên khi thêm graph mới.

2. **Không đặt `graph_service` bên trong `graphs/`.** Thành phần tạo run config và gọi `ainvoke` là một service, do đó nó phải nằm trong `services/`. Nếu đặt nó vào `graphs/`, package của graph sẽ chứa chính đối tượng gọi nó.

3. **Không import hai chiều (circular import) giữa các module tính năng.** `analyze → fill` *và* `fill → analyze` tạo thành một chu trình (cycle), và dù Python có thể chấp nhận thì cả hai module đều không thể đọc hiểu, viết test hay tách rời độc lập. Khi hai tính năng cần chung một thứ, thứ đó phải thuộc về tầng dưới của cả hai — nằm trong `app/common/` đối với từ vựng/domain model, hoặc `app/agent/` đối với cơ chế graph — chứ không nằm ở tính năng nào vô tình định nghĩa nó trước.

4. **Hai graph trong cùng một tính năng chia sẻ qua `graphs/shared/`.** Một helper mà graph thứ hai cần dùng tới thì không còn là của riêng graph thứ nhất nữa; việc import `graphs/graph_a/intake.py` từ `graph_b` sẽ gắn chặt hai graph với nhau vĩnh viễn. Việc chọn 1 trong 3 nơi để đặt helper chỉ cần xác định qua một lệnh grep:

   | Ai gọi nó | Nơi lưu trữ |
   |---|---|
   | Một graph duy nhất | `graphs/<graph_name>/<helper>.py` |
   | Nhiều graph, không có thành phần nào khác | `graphs/shared/<helper>.py` |
   | Cả service, route, hoặc WS handler | `utils/<helper>.py` |

   ```bash
   # mọi file import nó đều nằm dưới graphs/ → chuyển vào graphs/shared/
   grep -rln "session_soniox_context" app/<feature> | grep -v "/graphs/"
   ```

   Đặt tên module shared theo nội dung nó chứa, không đặt theo tên graph:
   ví dụ `graphs/shared/session_soniox_context.py`, tuyệt đối không đặt
   `graphs/shared/session_context.py` cạnh thư mục `graphs/session_context/`
   — người đọc không thể phân biệt được chúng trong một dòng import.

`app/agent/models.py` là file duy nhất chỉ định tên nhà cung cấp LLM (provider). Mọi thứ ở tầng trên đều nhận `ChatModel`, vì vậy không có node, prompt hay helper nào biết được nhà cung cấp nào đang trả lời.

---

## Các bước thêm một Graph mới

Mọi thứ dưới đây đều nằm trong tính năng mà graph trực thuộc — `app/<feature>/` — không bao giờ đặt trong `app/agent/`.

### 1. Đặt tên cho các node

`app/<feature>/enums/<feature>_graph_enums.py`

```python
class YourNodeName(StrEnum):
    PREPARE = "prepare"
    RESPOND = "respond"
```

### 2. Định nghĩa State

`app/<feature>/graphs/<graph_name>/state.py`

```python
class YourInput(TypedDict):
    content: str

class YourState(TypedDict):
    content: str
    draft: str

class YourOutput(TypedDict):
    draft: str
```

### 3. Viết các node và helper tương ứng

`app/<feature>/graphs/<graph_name>/nodes.py` — mỗi node là một class, nhận cấu hình qua `__init__`, điểm vào (entry point) của graph được đặt tên là `work`.

Bất kể một node thực sự *làm* gì — prompt, parse, duyệt tài liệu, định hình dữ liệu — đều được đưa vào một helper bên cạnh: `app/<feature>/graphs/<graph_name>/<helper>.py`, hoặc `app/<feature>/utils/<helper>.py` nếu một luồng khác cũng cần đến nó. **Không** đặt trong `services/`, cho dù nó nghe có vẻ giống một service.

### 4. Thiết lập Builder

`app/<feature>/graphs/<graph_name>/builder.py`

```python
def build(model: ChatModel, ...) -> CompiledStateGraph:
    graph = StateGraph(YourState, input_schema=YourInput, output_schema=YourOutput)
    graph.add_node(YourNodeName.RESPOND, RespondNode(model).work)
    graph.add_edge(START, YourNodeName.RESPOND)
    graph.add_edge(YourNodeName.RESPOND, END)
    return graph.compile()
```

### 5. Biên dịch một lần duy nhất (Compile once)

`app/<feature>/graphs/<graph_name>/registry.py` — singleton đã biên dịch, và là file duy nhất định nghĩa các cấu hình (settings) mà graph này đọc.

```python
YOUR_MODEL_PROFILE = ModelProfile(purpose=ModelPurpose.YOURS, ...)

def build_your_graph() -> CompiledStateGraph:
    return builder.build(model=build_chat_model(YOUR_MODEL_PROFILE), ...)

YOUR_GRAPH: CompiledStateGraph = build_your_graph()
```

### 6. Thêm service để chạy graph

`app/<feature>/services/<graph_name>_graph_service.py` — tạo run config, gọi `ainvoke`, trả về kết quả phản hồi. **File này tuyệt đối không nằm trong `graphs/`.**

### 7. Thêm route và schemas

Mỗi graph có endpoint riêng và schema request/response riêng. Một endpoint chung chung kiểu `POST /graphs/{graph_name}/run` sẽ đòi hỏi một union của mọi cấu trúc input từ tất cả các graph — các endpoint tường minh sẽ gọn gàng hơn là một bộ điều phối (dispatcher) duy nhất. Route import **service**, không bao giờ import graph.

### 8. Thêm kiểm thử (Tests) ⚠️ BẮT BUỘC

Xem [Kiểm thử (Testing)](#kiểm-thử-testing).

---

## Quy tắc về State

1. **Một file `state.py` duy nhất cho mỗi graph.** Không bao giờ phân tán state ra nhiều file — đây là hợp đồng duy nhất mà mọi node trong graph đó cùng chia sẻ.

2. **Không dùng chung base state giữa các agent.** Một base state dùng chung sẽ nhanh chóng biến thành tập hợp union của mọi trường mà bất kỳ agent nào từng cần, khiến mọi graph phải mang vác các trường mà nó không bao giờ đọc và hợp đồng của node trở nên mơ hồ. Dòng duy nhất thực sự dùng chung là `messages: Annotated[list[AnyMessage], add_messages]` — hãy viết lặp lại dòng này ở từng graph.

3. **Sử dụng `TypedDict`, không dùng Pydantic.** State dạng Pydantic sẽ validate lại sau mỗi super-step mà không mang lại lợi ích gì. Pydantic model chỉ thuộc về `schemas/`, tại ranh giới của API.

4. **Khai báo type annotation (với reducer) cho mọi key mà các nhánh rẽ song song (fan-out) có thể ghi vào.** Một key thông thường sẽ áp dụng cơ chế "ghi đè sau cùng" (last-write-wins), và nếu hai nhánh chạy song song cùng ghi đè vào đó, LangGraph sẽ raise `InvalidUpdateError` thay vì tự chọn một nhánh.

   ```python
   retrieved_ids: Annotated[list[str], operator.add]     # an toàn khi chạy song song
   node_outputs: Annotated[dict, merge_node_outputs]     # custom reducer
   ```

   Việc tự merge dữ liệu bên trong một node thay vì khai báo trong reducer là biến thể kinh điển của lỗi này.

5. **Giữ state nhỏ gọn.** Mọi trường dữ liệu đều được luân chuyển giữa các node và sao chép vào trace. Chỉ lưu trữ document id, không lưu trữ toàn bộ nội dung tài liệu.

6. **Ngữ cảnh tĩnh không phải là state.** `user_id`, locale và tenant không thay đổi trong suốt quá trình chạy — chúng thuộc về `config["configurable"]`. State chỉ dành cho những dữ liệu mà graph làm biến đổi (mutate).

7. **Khai báo `input_schema` / `output_schema` khi state chứa các trường mà caller không được phép thấy.** Thêm hai TypedDict bổ sung sẽ ngăn các trường tạm thời (scratch fields) rò rỉ vào response trả về. Có thể bỏ qua nếu state chỉ đơn thuần là `messages`.

---

## Quy tắc về Node

1. **Node đóng vai trò là một adapter, không phải nơi ôm đồm công việc.** Đọc state, gọi helper, trả về dict chứa state cập nhật cục bộ (partial state dict). Công việc thực tế nằm trong các helper của chính graph đó — không viết trực tiếp inline trong `work()`, và **không bao giờ nằm trong một service**: một node import từ `services/` đã đảo ngược cấu trúc phân tầng. Xem [Node không bao giờ import service](#tổng-quan).

   ```python
   from app.<feature>.graphs.<graph_name>.intake import parse_intake   # ✅ helper
   from app.<feature>.utils.mapping_input import build_input_text      # ✅ helper dùng chung
   from app.<feature>.services.intake_service import parse_intake      # ❌ graph → service
   ```

   Mỗi node đều là một class — xem [Class Nodes](#class-nodes).

2. **Chỉ trả về partial dict, không bao giờ trả về toàn bộ state.** `{"draft": text}`, không phải là một đối tượng state được dựng lại toàn bộ. Việc trả về toàn bộ state sẽ ghi đè và làm mất các thao tác ghi đồng thời (concurrent writes).

3. **Không bao giờ thay đổi trực tiếp (mutate) đối tượng `state` đầu vào.** LangGraph merge những gì bạn *return*. Việc thay đổi tại chỗ (in-place) sẽ vô hình đối với các reducer và gây ra race condition trong các nhánh chạy song song.

4. **Hãy để các reducer tự nối thêm (append).** Với `add_messages`, hãy return `{"messages": [new]}`. Việc return `existing + [new]` khiến reducer phải xử lý lại toàn bộ lịch sử ở mỗi lượt, và bất kỳ tin nhắn nào không có id cố định sẽ bị nhân bản (duplicate).

5. **Node id phải lấy từ enum `NodeName`.** Đây là các chuỗi ký tự được dùng trong `add_node`, `add_edge` và giá trị trả về của router — ba nơi mà lỗi chính tả (typo) rất dễ ẩn nấp.

6. **Tên node phải là duy nhất trên toàn bộ các graph.** Đặt tiền tố cho mỗi node — và mỗi symbol mà module node export — bằng tên của graph:

   ```python
   class SessionContextComposeNode(ComposeNode): ...   # ✅
   class SpeakersContextComposeNode(ComposeNode): ...  # ✅
   class ComposeNode: ...   # ❌ nếu xuất hiện ở bốn graph cùng lúc
   ```

   Bốn graph, mỗi graph đều sở hữu một `ComposeNode` có thể trông bình thường khi xem từng file riêng lẻ, nhưng sẽ gây khó khăn khi đọc traceback, khi dùng lệnh `grep`, hoặc trong một bài test import cả hai. Hàm `build()` trong `builder.py` là ngoại lệ duy nhất: nó luôn được truy cập thông qua module — ví dụ `session_context_builder.build(...)`.

   ```bash
   # lệnh này chỉ được phép in ra duy nhất chữ `build`
   grep -rh "^class \|^def \|^async def " app/*/graphs \
     | sed 's/.*\(class\|def\) \([A-Za-z_0-9]*\).*/\2/' | sort | uniq -d
   ```

7. **Những gì mọi compose node chia sẻ đều thuộc về base class.** Model, system prompt và bản thân lời gọi model là hoàn toàn giống nhau ở mọi graph — chúng nằm một lần duy nhất trong `app/agent/`; class con chỉ bổ sung prompt riêng, cách parse riêng và định nghĩa ý nghĩa khi xảy ra lỗi tại đó. Bốn bản copy của cùng một hàm `__init__` là dấu hiệu rõ ràng cho thấy đang thiếu base class.

8. **Không sử dụng hàm lồng nhau (nested functions).** Dependencies là các tham số truyền vào constructor của class node, không bao giờ dùng closure bao bọc state dạng `nonlocal`.

9. **Ưu tiên mệnh đề bảo vệ (guard clauses) thay vì lồng ghép if/else**, và không lặp lại logic khởi tạo giữa các nhánh rẽ.

---

## Class Nodes

**Mỗi node bắt buộc phải là một class.** Mặc dù LangGraph chấp nhận bất kỳ callable nào, dự án này chuẩn hóa việc dùng một class có method `work` được đăng ký làm node:

```python
class RespondNode:
    """Trả lời dựa trên ngữ cảnh cuộc hội thoại tính đến thời điểm hiện tại."""

    def __init__(self, model: Runnable, system_prompt: str):
        self.model = model
        self.system_prompt = system_prompt

    async def work(self, state: ChatState, config: RunnableConfig) -> dict:
        messages = [SystemMessage(content=self.system_prompt), *state["messages"]]
        reply = await self.model.ainvoke(messages, config)
        return {"messages": [reply]}
```

```python
respond = RespondNode(runnable, AgentConstants.CHAT_SYSTEM_PROMPT)
graph.add_node(NodeName.RESPOND, respond.work)
```

Lý do chọn class thay vì một module-level function được bind bằng `functools.partial`:

- Dependencies được **đặt tên rõ ràng (named)** thay vì truyền theo thứ tự (positional). `RespondNode(model, prompt)` tường minh và dễ đọc; `partial(respond, model, prompt)` thì không.
- Cùng một loại node có thể được **khởi tạo nhiều lần** trong một graph với các cấu hình khác nhau, đáp ứng linh hoạt yêu cầu khi ráp workflow.
- Thỏa mãn quy tắc "không dùng hàm lồng nhau" mà không cần tầng trung gian của `partial` — xem Quy tắc về phong cách hàm (Function Style Rules).

> ### ⚠️ `self` chỉ dùng để lưu cấu hình
>
> Graph đã biên dịch là một **singleton trên toàn bộ tiến trình (process-wide singleton)** — được dựng một lần duy nhất khi import trong `registry.py`, dùng chung cho mọi request, user và thread.
>
> `self` chỉ được phép lưu giữ những gì được truyền vào `__init__` và **không được chứa gì khác**. Ngay khi một node ghi dữ liệu theo từng request vào `self`, bạn sẽ gặp lỗi rò rỉ dữ liệu chéo giữa các user (cross-user data leak) mà không bài test đơn lẻ nào bắt được và chỉ bộc lộ khi có concurrency (truy cập đồng thời). Dữ liệu riêng của request bắt buộc phải nằm trong state dict hoặc trong config, không bao giờ lưu trên instance.
>
> Bài test `test_node_instances_hold_config_not_request_state` được viết để kiểm chứng điều này.

---

## Không sử dụng Tools

Các agent chỉ gọi model và không làm gì khác. Không có `ToolNode`, không có `bind_tools`, và không có `create_react_agent`.

Đây là lý do tại sao cả hai graph đều là `StateGraph` thuần túy: vòng lặp ReAct dựng sẵn sinh ra là để chạy chu trình gọi tool (tool-calling cycle), và khi không có tool thì nó chỉ là một lời gọi model thông thường được bọc trong lớp vỏ rườm rà. Thiết kế này cũng giữ cho tầng graph hoàn toàn sạch sẽ khỏi bất kỳ import database nào — không có package `graphs/` nào chạm tới ORM, đó là lý do tại sao các bài test có thể chạy mà không cần database.

**Nếu tools được thêm trở lại trong tương lai**, hai vấn đề sau sẽ quay lại cùng với chúng:

1. Một tool bắt buộc phải tự mở `SessionLocal()` ngắn hạn của riêng nó thay vì bao đóng (closing over) session của request, và phải lấy thông tin định danh từ `config["configurable"]`. **Tuyệt đối không đưa `Session`, API key hay chuỗi JWT thô vào `configurable`** — một Session không thể serialize được, và secret không có lý do gì để xuất hiện trong trace log.

2. `create_react_agent` **sẽ âm thầm loại bỏ fallbacks khi có tools**. Nó gọi `bind_tools` trực tiếp trên model, và `RunnableWithFallbacks` sẽ chỉ proxy lời gọi đó đến primary model, khiến fallback bị hủy bỏ. Giải pháp khắc phục là sử dụng dạng model động (callable model), dạng này LangGraph sẽ giữ nguyên khi truyền qua — đồng nghĩa với việc tools phải được bind từ trước:

   ```python
   bound = model.bind_tools(TOOLS).with_fallbacks([fallback.bind_tools(TOOLS)])
   create_react_agent(partial(resolve_model, bound), TOOLS, ...)
   ```

   Khi không có tools, cạm bẫy này không xảy ra, và cú pháp `model.with_fallbacks([fallback])` hoạt động trực tiếp hoàn hảo.

---

## Models và Fallback

Gateway tương thích chuẩn OpenAI, do đó `ChatOpenAI` giao tiếp với nó thông qua `base_url`. Cấu hình được thiết lập theo từng môi trường và nằm trong settings, không bao giờ đặt trong constants.

| Cài đặt (Setting)          | Ghi chú                                     |
|----------------------------|---------------------------------------------|
| `LLM_BASE_URL`             | Kết thúc bằng `/v1`                         |
| `LLM_API_KEY`              | Bearer token                                |
| `LLM_X_API_KEY`            | Gửi dưới dạng header `x-api-key`            |
| `LLM_MODEL_<PURPOSE>`      | Một model cho mỗi mục đích, vd: `LLM_MODEL_ANALYZER` |
| `*_FALLBACK`               | Mỗi trường mặc định lấy theo giá trị của primary |

`models.build_pair(profile)` trả về cặp `(primary, fallback)`. Vì mọi trường fallback đều kế thừa từ primary, nên nếu chỉ cấu hình fallback model thì hệ thống sẽ chuyển đổi dự phòng sang một model khác trên cùng gateway; còn nếu cấu hình `LLM_BASE_URL_FALLBACK` thì nó sẽ chuyển hẳn sang một endpoint riêng biệt.

> Một cấu hình fallback mà mọi giá trị đều giống hệt primary sẽ chẳng bảo vệ được gì ngoại trừ một sự cố chớp nhoáng (transient blip). Hãy trỏ nó tới một endpoint hoặc một model khác. Một mục đích (purpose) mà không thiết lập bất kỳ trường fallback nào sẽ **không có** fallback, chứ không tạo ra bản sao trùng lặp của primary.

Việc bọc wrapper là đủ vì không có tool nào cần bind — xem [Không sử dụng Tools](#không-sử-dụng-tools) để biết cạm bẫy sẽ quay lại nếu điều đó thay đổi.

```python
runnable = model.with_fallbacks([fallback]) if fallback else model
```

### ⚠️ Cơ chế Failover diễn ra âm thầm — hãy tự ghi Log

`RunnableWithFallbacks` **không ghi bất kỳ log nào** khi primary model thất bại. Một hàm health check điều hướng vòng qua primary trước khi gọi nó cũng không ghi log. Nếu bỏ mặc, toàn bộ request có thể được trả lời bởi fallback model mà không có một dòng log nào thông báo, và câu hỏi tiếp theo — *"model nào đã sinh ra kết quả sai lệch này?"* — sẽ không có lời giải đáp.

Do đó, mỗi lần chuyển đổi dự phòng (failover) bắt buộc phải ghi log một lần, ngay tại ranh giới nắm được thông tin:

```python
answered_by = reply.response_metadata.get(MODEL_NAME_METADATA_KEY, "")
if answered_by and answered_by != self.profile.primary_model:
    logger.warning(FALLBACK_MODEL_ANSWERED_MESSAGE, purpose, primary_model, answered_by)
```

Điều tương tự cũng áp dụng cho bất kỳ cơ chế failover tự viết nào: một khối `except Exception:` trống rỗng bọc quanh retry chính là biến thể của lỗi này, nó che giấu một sự cố ngừng hoạt động vĩnh viễn (permanent outage). Nếu bạn viết code failover, bạn phải viết kèm lệnh log.

### Lời gọi Model là một ranh giới lỗi (Failure Boundary)

Khi mọi upstream trong chuỗi đều sập, exception class riêng của provider sẽ bắn thẳng về phía caller — và global handler không nhận biết được nó, khiến một sự cố gateway thực sự lại bị báo cáo thành lỗi không rõ nguyên nhân `ERR.SYS0101`. Hãy chuyển đổi exception một lần duy nhất tại đây:

```python
try:
    return await self.runnable.ainvoke(messages)
except Exception as exc:
    logger.error(MODEL_CHAIN_EXHAUSTED_MESSAGE, purpose, primary_model, type(exc).__name__, exc)
    raise InternalServerException(ErrorConstants.Agent.MODEL_REQUEST_FAILED) from exc
```

Duy nhất một khối `try`, tại đúng ranh giới này — không bọc riêng lẻ từng node. Hãy giữ lại `from exc`: nguyên nhân gốc (cause) là dấu vết duy nhất ghi lại điều gì thực sự đã hỏng.

Các bài test `test_chat_falls_back_when_the_primary_fails`, `test_without_a_fallback_the_error_still_raises` và `test_an_exhausted_chain_raises_the_typed_error_the_handler_knows` đảm bảo kiểm soát chặt chẽ cả ba tình huống này.

---

## Truyền luồng dữ liệu (Streaming)

SSE là ngoại lệ duy nhất được ghi nhận đối với quy tắc `DataResponseAPI`: một luồng sự kiện (event stream) là một chuỗi các frame liên tiếp, do đó body không thể là một tài liệu JSON đơn lẻ. **Lớp bọc (envelope) được chuyển từ body vào từng frame riêng biệt.**

```
event: token
data: {"status": "success", "data": "Hel"}

event: done
data: {"status": "success"}
```

- Đóng gói frame bằng `format_sse(event, payload)`; tên event lấy từ enum `AgentEvent`.
- Xử lý agent, config và messages **sớm ngay trong route** thông qua `prepare_chat_stream`, trước khi trả về `StreamingResponse`. Các tác vụ phụ thuộc vào scope của request không được phép nằm bên trong generator chạy sau khi route handler đã return.
- Lỗi xảy ra giữa chừng luồng (mid-stream failure) sẽ phát ra một frame `error`; lúc này headers đã được gửi đi nên không thể raise exception được nữa.

---

## LangSmith

Giám sát và truy vết (tracing) **không cần code tích hợp đặc thù**. Thư viện `langsmith` đi kèm sẵn thông qua dependency `langchain-core`, đọc cấu hình trực tiếp từ `os.environ`, và tự động gắn instrumentation cho mọi lời gọi LangChain cũng như LangGraph. Chỉ cần thiết lập các biến môi trường, các trace sẽ tự động xuất hiện — thời gian chạy từng node, lời gọi tool, số lượng token, chi phí.

### Biến môi trường

| Biến                   | Mục đích                                           |
|------------------------|----------------------------------------------------|
| `LANGSMITH_TRACING`    | `true` để bật tracing. Mọi giá trị khác đều là tắt.|
| `LANGSMITH_API_KEY`    | Thông tin xác thực LangSmith (API Key)              |
| `LANGSMITH_PROJECT`    | Trace bucket, ví dụ `javis-base-dev`               |
| `LANGSMITH_ENDPOINT`   | `https://api.smith.langchain.com`, hoặc URL tự host|

SDK sẽ phân giải từng biến theo namespace `LANGSMITH_` trước, sau đó mới đến namespace cũ `LANGCHAIN_` — các biến `LANGCHAIN_TRACING_V2` và `LANGCHAIN_PROJECT` vẫn hoạt động, nhưng nên ưu tiên tiền tố `LANGSMITH_` trong các cấu hình mới.

> ⚠️ **Các cờ được so sánh chính xác với chuỗi ký tự `"true"`.** Các giá trị `True`, `1`, `TRUE` và `yes` đều bị coi là *tắt* một cách âm thầm. Quy tắc này áp dụng cho cả `LANGSMITH_TRACING` và cả hai cờ ẩn dữ liệu bên dưới.

**Các biến này không đưa vào `Settings`.** SDK đọc trực tiếp biến môi trường của process, do đó nếu ánh xạ chúng vào pydantic-settings sẽ chỉ làm dư thừa các trường không ai dùng. Chúng chỉ nên nằm trong file `.env` hoặc compose env.

### Những gì chúng ta cần viết trong code

Chỉ có một thứ xứng đáng phải viết thêm code: thông tin định danh cho từng request, để khi có báo cáo về một câu trả lời kém chất lượng, trace có thể được liên kết ngược trở lại với chính lượt chạy đã sinh ra nó. Thông tin này được gắn vào config mà service đã tạo sẵn — xem hàm `run_config`:

```python
return {
    "configurable": context,
    "run_name": traced_run_name(name, run_id),   # <tên_graph>_<id>_<UTC timestamp>
    "tags": [settings.app_env, name, *(tags or [])],
    "metadata": metadata,
}
```

- **`run_name`** — **gồm tên graph, run id và thời gian**, ví dụ `session_context_6d662627-5021-42d0-991b-e4bc9b09c1fe_20260826T045627Z`. Nếu chỉ dùng tên graph thông thường thì mọi dòng trong danh sách trace sẽ giống hệt nhau, khiến bạn không thể tìm ra lượt chạy cụ thể đang gặp lỗi. Id này phải là id **truy vết ngược về hệ thống của chúng ta** — id trả về trong response, id lưu trữ step trace, hoặc `project_id` / `session_id` mà caller gửi lên. Một id chỉ tồn tại bên trong LangSmith thì cũng vô dụng như không có id.
- **`tags`** — môi trường (environment) và tên graph **gốc**, kèm API nếu một graph phục vụ nhiều API. Tuyệt đối không đưa run name duy nhất vào tags: một facet phân loại mà mỗi giá trị chỉ có đúng một bản ghi thì không còn ý nghĩa phân loại. Đó là lý do name và tags được xây dựng từ các tham số riêng biệt.
- **`metadata`** — mọi id bạn sẽ thực sự dùng để tìm kiếm, bao gồm id của chính caller (`template_id`, `project_id`, `session_id`) nếu request có truyền. Vì server không lưu trữ trạng thái, một trace chính là bằng chứng *duy nhất* ghi nhận lượt chạy đó đã xảy ra. Điều này làm cho tracing ở đây quan trọng hơn nhiều so với hệ thống có checkpointer.

> Id của caller chỉ có thể vào được trace nếu request schema có trường tương ứng. Thêm một trường là thay đổi API — hãy thống nhất trước khi cam kết liên kết dữ liệu.

**Một project duy nhất, gắn tag theo từng agent.** Việc chia nhỏ project cho mỗi agent sẽ phân mảnh giao diện theo dõi trace và nhân bản cấu hình môi trường. Chỉ chia project khi bạn thực sự cần dashboard riêng biệt hoặc hạn mức (quota) riêng cho từng agent.

### Thoát dữ liệu ra ngoài (Data egress) ⚠️

Khi bật tracing, **toàn bộ prompts, tin nhắn người dùng, input của tool và output của model sẽ rời khỏi hạ tầng của bạn** để gửi tới LangSmith Cloud, và có thể được lưu trữ hoặc lập chỉ mục sau khi xóa. Hãy thống nhất chính sách bảo mật trước khi tính năng này tiếp cận người dùng thật:

| Chính sách                 | Cách thực hiện                                       |
|----------------------------|------------------------------------------------------|
| Chỉ dùng ở môi trường Dev  | Đặt `LANGSMITH_TRACING` ở `dev` và không bật ở môi trường khác |
| Chỉ gửi Metadata, không gửi nội dung | `LANGSMITH_HIDE_INPUTS=true` và `LANGSMITH_HIDE_OUTPUTS=true` |
| Đầy đủ nội dung, tự host hạ tầng | Trỏ `LANGSMITH_ENDPOINT` tới instance riêng của bạn |

Các cờ ẩn dữ liệu giúp giữ lại thông tin về thời gian thực thi, số lượng token, chi phí và cấu trúc luồng của graph trong khi loại bỏ toàn bộ nội dung payload. Nếu muốn che giấu/ẩn thông tin nhạy cảm (redaction) thay vì xóa bỏ hoàn toàn, `Client` cũng hỗ trợ `hide_inputs` / `hide_outputs` dưới dạng một callable `(dict) -> dict`.

**Mặc định là gửi toàn bộ nội dung ra bên ngoài.** Bật tracing là một quyết định về an toàn dữ liệu, không đơn thuần chỉ là thao tác vận hành (ops).

### Kiểm tra xem tracing đã được bật chưa

Tracing mặc định là tắt trừ khi có cấu hình `LANGSMITH_TRACING=true`:

```python
from langsmith.utils import tracing_is_enabled
print(tracing_is_enabled())
```

---

## Xử lý Lỗi (Errors)

Tuân theo mô hình chuẩn — constant, định nghĩa YAML trong cả ba ngôn ngữ (locale), typed exception, và global handler sẽ format response.

| Constant                       | Key                          | Mã lỗi (Code)|
|--------------------------------|------------------------------|--------------|
| `Agent.MODEL_REQUEST_FAILED`   | `agent_model_request_failed` | ERR.AGT0101  |

`ErrorConstants.Agent` được dùng chung bởi mọi graph, do đó nó chỉ chứa những lỗi mà bước gọi model dùng chung phát ra. Lỗi thuộc về một tính năng riêng biệt sẽ giữ nguyên namespace của tính năng đó — ví dụ `ErrorConstants.Analysis`, `ErrorConstants.DocFiller`.

**Một khối `try` duy nhất cho mỗi ranh giới lỗi** — lời gọi model chính là ranh giới lỗi. Không bọc `try` ở từng node riêng lẻ; hãy để các typed exception lan truyền tự nhiên tới global handler.

> ⚠️ **Một raw exception từ provider không phải là một typed error.** Global handler chỉ bắt các ngoại lệ kế thừa từ `AppHTTPException`; bất kỳ ngoại lệ nào khác sẽ rơi vào trường hợp mặc định `ERR.SYS0101 Internal server error` kèm theo traceback, khiến sự cố gián đoạn từ gateway trông giống như một lỗi bug trong source code của chúng ta. Xem [Lời gọi Model là một ranh giới lỗi](#lời-gọi-model-là-một-ranh-giới-lỗi-failure-boundary).

> ⚠️ **Các nhánh chạy song song có thể che lấp lỗi của nhau.** Khi cả nhánh fan-out và nhánh gọi model đều gặp lỗi, LangGraph sẽ hiển thị lỗi của một trong hai — vì vậy lỗi xử lý tài liệu có thể bị hiển thị nhầm thành sự cố gián đoạn model. Nếu việc phát hiện lỗi sớm (fail-first) quan trọng hơn độ trễ (latency) đối với một nhánh nào đó, hãy đưa nó trở lại luồng chạy tuần tự (sequential edge).

---

## Kiểm thử (Testing)

File `tests/test_agent_graphs.py` chạy hoàn toàn với các đối tượng giả lập (fakes) — không cần database, không cần kết nối mạng, không cần gateway key.

```bash
pytest tests/test_agent_graphs.py
```

Thay thế gateway bằng một fake chat model:

```python
def fake(*replies: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(r) for r in replies]))
```

Các ca kiểm thử tối thiểu bắt buộc phải bao phủ:

1. **Chuyển đổi dự phòng (Failover)** — primary ngừng hoạt động được cứu bởi fallback, không có fallback thì vẫn raise exception, và khi chuỗi cạn kiệt thì bắn ra lỗi *định kiểu (typed error)*.
2. **Log của failover** — assert bản ghi log thực tế, không chỉ kiểm tra kết quả trả về. Một cơ chế failover âm thầm vẫn có thể vượt qua mọi bài test hành vi thông thường.
3. **Tính phi trạng thái (Statelessness)** — lượt chạy thứ hai không nhìn thấy bất kỳ state nào của lượt chạy thứ nhất.
4. **Lịch sử từ client (Client history)** — các lượt hội thoại được gửi lại phải đến graph đúng theo thứ tự thời gian.
5. **Output schema** — các trường state nội bộ không được phép rò rỉ ra kết quả trả về cho client.
6. **Đặt tên cho lượt chạy (Run naming)** — run name bắt buộc phải chứa id, và các tag phải giữ tính ổn định.

Một fake chat model chỉ chứng minh được cấu trúc kết nối mã nguồn (the wiring), chứ không chứng minh được đường truyền thực tế (the wire). Mỗi khi có thay đổi quan trọng, hãy trỏ primary vào một URL không tồn tại và trỏ fallback vào một HTTP gateway nội bộ để thực hiện một cuộc gọi thật: đó là cách duy nhất để quan sát cơ chế retry của SDK, những gì gateway thực sự nhận được, và những dòng log nào được ghi lại.

---

## Danh sách kiểm tra (Checklist)

Trước khi commit bất kỳ thay đổi nào liên quan đến graph, hãy đảm bảo:

**Phân tầng kiến trúc (Layering)** — phần thường hay bị bỏ sót nhất
- [ ] Lệnh `grep -rn "from app\..*\.services" app/*/graphs` cho kết quả **rỗng** — không có node, builder hay registry nào import một service.
- [ ] Mọi thứ chuyển ra khỏi `services/` đều đã được đưa vào thư mục graph (chỉ graph này gọi), vào `graphs/shared/` (nhiều graph cùng gọi) hoặc vào `utils/` (thành phần ngoài `graphs/` cũng gọi).
- [ ] Không có graph nào import thư mục của một graph khác — phần dùng chung đã được chuyển sang `graphs/shared/`, đặt tên theo nội dung chức năng chứ không đặt theo tên graph.
- [ ] Graph service nằm trong `services/`, **không** nằm trong `graphs/`.
- [ ] Graph có thư mục con riêng: `graphs/<graph_name>/`.
- [ ] Không có import mới giữa các module tính năng — kiểm tra kỹ ở **cả hai** chiều.
- [ ] `app/agent/` không bị thêm bất kỳ thành phần nào mang domain của tính năng cụ thể.

**Bản thân Graph**
- [ ] Đã thêm mục định nghĩa trong enum `NodeName`; id của node không bao giờ dùng chuỗi ký tự thô (hardcoded string).
- [ ] Toàn bộ state nằm trong một file `state.py`; mọi key trong luồng rẽ nhánh song song (fan-out) đều có reducer.
- [ ] Các node chỉ trả về partial dict và không bao giờ làm biến đổi trực tiếp `state` đầu vào.
- [ ] Mỗi node đều là một class; `self` chỉ lưu cấu hình và tuyệt đối không lưu dữ liệu riêng của từng request.
- [ ] Tên các node là duy nhất trên toàn bộ các graph — lệnh `uniq -d` chỉ in ra duy nhất chữ `build`; các logic chung giữa các compose node được kế thừa từ base class thay vì copy-paste.
- [ ] Không lưu trữ dữ liệu mới vào DB — nếu bắt buộc phải lưu, đó là một thay đổi về mặt thiết kế.
- [ ] Đã đăng ký trong `registry.py`, đồng thời tạo route và các schema tương ứng.

**Model, Lỗi, Tracing**
- [ ] Nhà cung cấp model chỉ được nêu tên duy nhất trong `app/agent/models.py` và không ở đâu khác.
- [ ] Mọi lần failover đều ghi log đúng một lần; không dùng khối `except` trống rỗng bọc quanh retry.
- [ ] Khi chuỗi model cạn kiệt phải raise typed error kèm theo `from exc`.
- [ ] Đã khai báo mã lỗi trong `ErrorConstants` và **cả ba** file ngôn ngữ (locale files).
- [ ] `run_name` mang id có thể truy vết ngược về hệ thống; các tag giữ tính ổn định.
- [ ] Nếu bật tracing, chính sách `LANGSMITH_HIDE_*` đã được thống nhất cho các môi trường ngoài dev.

**Kiểm thử (Tests) ⚠️**
- [ ] Đã kiểm thử Failover, **log** của failover, tính phi trạng thái (statelessness), output schema, run naming.
- [ ] Đã chạy thử ít nhất một cuộc gọi thật với primary trỏ vào URL lỗi và fallback trỏ vào gateway local.
- [ ] Đã chạy `ruff format` và `ruff check` sạch sẽ trên toàn bộ các file được chỉnh sửa.
- [ ] Toàn bộ test cases đều PASS.
