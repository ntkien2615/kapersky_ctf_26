# Kaspersky CTF — Solutions & Writeups

Repository chứa mã nguồn đề bài, công cụ phân tích và kịch bản khai thác / giải mã (exploit & solve scripts) cho các thử thách tại **Kaspersky CTF**.

---

## 📌 Tổng quan các thử thách (Challenges Overview)

| Thử thách (Folder) | Thể loại | Trạng thái | Writeup Chi tiết | Lời giải (Solve Script) | Flag |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **[lumberjack](./lumberjack/)** | AI / ML |  Hoàn thành | [writeup.md](./lumberjack/writeup.md) | [solve.py](./lumberjack/solve.py) | `kaspersky{c873202d-c2ff-4469-a1fe-8718bac77f39}` |
| **[garden](./garden/)** | Web |  Hoàn thành | [writeup.md](./garden/writeup.md) | [solve.py](./garden/solve.py) | *(Khai thác Blind SQLi từ database)* |
| **[censoredcrypt](./censoredcrypt/)** | Crypto |  Hoàn thành | [writeup.md](./censoredcrypt/writeup.md) | [solve.py](./censoredcrypt/solve.py) | *(Khôi phục private key qua LLL)* |
| **[riffle-royale](./riffle-royale/)** | Crypto |  Hoàn thành | [writeup.md](./riffle-royale/writeup.md) | [solve.py](./riffle-royale/solve.py) | *(Khôi phục Elliptic Curve)* |
| **[sudocrypt](./sudocrypt/)** | Crypto |  Hoàn thành | [writeup.md](./sudocrypt/writeup.md) | [solve.py](./sudocrypt/solve.py) | *(Tấn công đại số GF(4093))* |

---

## 🔍 Tóm tắt phương pháp giải (Technical Writeups)

### 1. Lumberjack (`lumberjack`)
* **Lỗ hổng:** Out-of-bounds leaf evaluation trong toán tử `TreeEnsembleClassifier` của ONNX Runtime.
* **Cách giải:** Xây dựng mô hình ONNX tùy chỉnh truy vấn các `feature_id` mang giá trị âm để đọc rò rỉ vùng nhớ `.rodata`/vùng nhớ chứa cờ của tiến trình server. Sử dụng cấu trúc cây 8 nhánh và thuật toán tìm kiếm nhị phân đa phân đoạn (multi-interval search) để trích xuất từng 4-byte chunk dữ liệu cho đến khi thu được toàn bộ flag.
* **Flag thu được:** `kaspersky{c873202d-c2ff-4469-a1fe-8718bac77f39}`.

---

### 2. Garden (`garden`)
* **Lỗ hổng:** Boolean Blind SQL Injection thông qua Flask session cookie (`user_id`).
* **Cách giải:** Server cho phép ký lại session cookie bằng secret key mặc định trong code. Kẻ tấn công chèn payload SQLi vào trường `user_id`. Khi điều kiện đúng, câu lệnh thực thi nước đi cờ Shogi (`7g7f`); khi điều kiện sai, hàm `json_extract('{', '$')` gây lỗi khiến nước đi không được ghi nhận. Bằng cách so sánh trạng thái bàn cờ (SFEN) sau mỗi lượt, ta xây dựng được True/False Oracle để dò từng ký tự của flag từ bảng `game_moves`.

---

### 3. CensoredCrypt (`censoredcrypt`)
* **Lỗ hổng:** Partial Nonce Leakage dẫn tới bài toán Hidden Number Problem (HNP).
* **Cách giải:** Các thông số chẩn đoán (telemetry/profile) để lộ thông tin xấp xỉ về giá trị nonce $k$ dùng trong chữ ký điện tử. Từ các mẫu chữ ký thu thập được, ta thiết lập hệ cơ sở mạng lattice và sử dụng thuật toán rút gọn mạng LLL kết hợp thuật toán Babai Nearest Plane (CVP) để khôi phục chính xác khóa bí mật $x$, từ đó giả mạo chữ ký cho thông điệp mục tiêu.

---

### 4. Riffle Royale (`riffle-royale`)
* **Lỗ hổng:** Khôi phục tham số đường cong Elliptic Curve từ chuỗi hoành độ (x-coordinates) bị đan xen.
* **Cách giải:** Sử dụng các phương trình đại số liên hệ giữa 3 hoành độ liên tiếp $x_{i-1}, x_i, x_{i+1}$ trên đường cong Weierstrass. Tính toán đa thức Resultant và lấy ước chung lớn nhất (GCD) giữa các hệ số để suy ra trường hữu hạn $\mathbb{F}_p$ và các hệ số $(a, b)$ của đường cong elliptic. Sau khi có đường cong, thực hiện phép nhân điểm (scalar multiplication) để tính toán chính xác giá trị tại chỉ số mong muốn.

---

### 5. SudoKrypt (`sudocrypt`)
* **Lỗ hổng:** Cấu trúc PRNG SpectrumGenerator có quan hệ truy hồi tuyến tính (Linear Recurrence) trên trường con $\text{GF}(4093)$.
* **Cách giải:** 
  1. Gửi bản rõ chọn trước (Chosen-Plaintext) để bóc tách hoán vị `q_perm` và triệt tiêu độ lệch xoay vòng (rotation ambiguity).
  2. Bóc tách các giá trị luồng PRNG cho từng khối.
  3. Xây dựng đa thức đặc trưng bậc 56 trên $\text{GF}(4093)$ và giải hệ ma trận Vandermonde để khôi phục hoàn chỉnh các vector hệ số ban đầu của PRNG.
  4. Đồng bộ hóa bộ tạo số ngẫu nhiên tới block 96, thực hiện hàm `fold_for_flag()` và giải mã tất cả các khối flag.

---

## 🛠️ Yêu cầu môi trường (Prerequisites)

Để chạy thử các script giải, khuyến nghị môi trường Python 3.10+ cùng các thư viện:
```bash
pip install requests pycryptodome gmpy2 onnx
```
*(Lưu ý: Đối với bài `CensoredCrypt`, cần cài đặt `gmpy2` để tính toán số học độ chính xác cao trên Lattice).*
