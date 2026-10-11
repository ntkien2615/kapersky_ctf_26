# Writeup: Lumberjack.AI

- **Category:** AI / Machine Learning
- **Difficulty:** Medium / Hard
- **Flag:** `kaspersky{c873202d-c2ff-4469-a1fe-8718bac77f39}`

---

## 1. Tổng quan đề bài

Đề bài cung cấp một tệp thực thi ELF (`092c1add57f24a93362a1adc3e6abed3`) và một mô hình mẫu định dạng ONNX (`sample.onnx`). Server nhận tệp ONNX do người chơi tải lên, thực thi suy luận (inference) bằng ONNX Runtime và trả về kết quả dự đoán (predicted class/probabilities). Mục tiêu là trích xuất flag bí mật nằm trong không gian bộ nhớ của tiến trình.

---

## 2. Phân tích lỗ hổng (Vulnerability Analysis)

Mô hình ONNX sử dụng toán tử **`TreeEnsembleClassifier`** thuộc domain `ai.onnx.ml`. Toán tử này lưu trữ các thuộc tính của cây quyết định:
- `nodes_featureids`: Danh sách chỉ số đặc trưng (feature index) mà mỗi nút kiểm tra.
- `nodes_values`: Giá trị ngưỡng (thresholds) tại mỗi nút.
- `nodes_modes`: Phép so sánh (`BRANCH_LEQ`, `BRANCH_LT`,...).
- `nodes_truenodeids` & `nodes_falsenodeids`: Chỉ số nút con tiếp theo.
- `class_nodeids`, `class_ids`, `class_weights`: Trọng số và nhãn lớp đầu ra tại các nút lá.

### Điểm yếu (Out-of-Bounds Memory Read):
Khi đánh giá điều kiện rẽ nhánh:
```cpp
float val = input_tensor[feature_id];
if (val <= threshold) { ... }
```
Toán tử không kiểm tra cận dưới của `feature_id`. Khi thiết lập `feature_id < 0`, phép toán `input_tensor[feature_id]` truy cập ngược vào vùng nhớ trước bộ đệm đầu vào (out-of-bounds read). Vùng nhớ này chứa dữ liệu `.rodata` hoặc biến nhớ bí mật của tiến trình, trong đó có chuỗi flag.

---

## 3. Kỹ thuật khai thác (Exploitation)

Giá trị tại vị trí rò rỉ là 4 byte (tương ứng với kiểu `float32` hoặc `uint32`). Ta cần đọc giá trị 32-bit này bằng kênh thông tin phản hồi (Oracle) là nhãn lớp (class label).

### Phân đoạn 8 nhánh (Octary Search):
Thay vì tìm kiếm nhị phân 1 bit mỗi lượt (2 nhánh), ta tối ưu số lượt truy vấn bằng cách tạo cây quyết định 8 khoảng (7 ngưỡng: $t_0 < t_1 < \dots < t_6$):
* Khoảng 0: $x \le t_0 \implies$ Class 0
* Khoảng 1: $t_0 < x \le t_1 \implies$ Class 1
* ...
* Khoảng 7: $x > t_6 \implies$ Class 7

Mỗi lượt truy vấn thu được $\log_2(8) = 3$ bits dữ liệu. Để dò một giá trị 32-bit ($0 \dots 2^{32}-1$), chỉ cần khoảng 11 lượt truy vấn HTTP.

### Dò chuỗi Flag:
Vùng cờ nằm ở dải `feature_id` từ `-20` đến `-9` (tương ứng offset cách nhau mỗi 4 byte). Script [solve.py](./solve.py) tự động:
1. Đóng gói payload nhị phân protobuf tạo cấu trúc ONNX runtime hợp lệ mà không cần cài đặt protobuf compiler đầy đủ.
2. Với mỗi `feature_id` từ `-20` tới `-9`, thực hiện tìm kiếm nhị phân / phân đoạn 8 nhánh để khôi phục 4 byte giá trị.
3. Ghép các byte thu được lại thành chuỗi flag hoàn chỉnh.

---

## 4. Thực thi

```bash
python solve.py
```

Kết quả:
```
Current flag so far: b'kaspersky{c873202d-c2ff-4469-a1fe-8718bac77f39}\x00'
Found end of flag! Finished extraction!
FLAG: kaspersky{c873202d-c2ff-4469-a1fe-8718bac77f39}
```
