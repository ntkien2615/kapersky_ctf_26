# Writeup: CensoredCrypt

- **Category:** Cryptography
- **Difficulty:** Hard
- **Techniques:** Biased Nonce / Hidden Number Problem (HNP), Lattice Reduction (LLL), Babai Nearest Plane (CVP), Schnorr Signature Forgery

---

## 1. Tổng quan đề bài

Đề bài cung cấp dịch vụ mạng triển khai hệ thống chữ ký dạng Schnorr qua socket TCP. Người chơi có thể:
1. `PUB`: Lấy khóa công khai $Y = G^x \pmod P$ và thông số cân chỉnh (`calibration`).
2. `SIGN <hex>`: Ký tối đa 48 thông điệp tùy ý (ngoại trừ thông điệp đích `give_me_gift`).
3. `SUBMIT <hex> <R> <s>`: Gửi chữ ký hợp lệ cho thông điệp `give_me_gift` để nhận flag.

---

## 2. Phân tích mật mã (Cryptanalysis)

### 2.1. Cấu trúc chữ ký & Diagnostics
Khi người dùng gọi `SIGN`:
- Server sinh số ngẫu nhiên nonce $k \in [1, Q-1]$.
- Cam kết $R = G^k \pmod P$.
- Giá trị thử thách $e = \text{Hash}(M \parallel R) \pmod Q$.
- Phản hồi $s = (k + e \cdot x) \pmod Q$.

Điểm yếu nằm ở dữ liệu chẩn đoán (`diagnostics`) đi kèm:
- Server trả về các trường `patch`, `resid`, `health` được tính từ quỹ đạo góc của nonce $k$.
- Bằng hàm nghịch đảo quỹ đạo `invert_profile()` trong [solve.py](./solve.py), ta có thể ước lượng giá trị góc $\theta$ và thu được giá trị xấp xỉ của nonce:
  $$k = k_{\text{est}} + \delta$$
  với sai số $|\delta|$ rất nhỏ so với modulo $Q$.

### 2.2. Đưa về bài toán số ẩn (Hidden Number Problem - HNP)
Với $m$ cặp chữ ký $(e_i, s_i)$:
$$s_i \equiv k_i + e_i x \pmod Q$$
Thay $k_i = k_{\text{est}, i} + \delta_i$:
$$s_i - k_{\text{est}, i} \equiv \delta_i + e_i x \pmod Q$$
Nhân hai vế với $e_0^{-1} \pmod Q$ và triệt tiêu biến bí mật $x$, ta thiết lập được hệ phương trình tuyến tính cho các sai số $\delta_i$:
$$\delta_i - A_i \delta_0 \equiv C_i \pmod Q$$

### 2.3. Giải bằng mạng Lattice (LLL + Babai CVP)
Ta xây dựng ma trận cơ sở mạng lattice:
$$B = \begin{pmatrix}
Q & 0 & \dots & 0 & 0 \\
0 & Q & \dots & 0 & 0 \\
\vdots & \vdots & \ddots & \vdots & \vdots \\
0 & 0 & \dots & Q & 0 \\
A_1 & A_2 & \dots & A_{m-1} & 1
\end{pmatrix}$$
và vector đích:
$$T = (-C_1, -C_2, \dots, -C_{m-1}, 0)$$

Sử dụng thuật toán rút gọn cơ sở **LLL (Lenstra–Lenstra–Lovász)** và thuật toán tìm vector gần nhất **Babai Nearest Plane (CVP)**:
- Tìm được $\delta_0$.
- Suy ra nonce $k_0 = (k_{\text{est}, 0} + \delta_0) \pmod Q$.
- Khôi phục khóa bí mật:
  $$x = (s_0 - k_0) \cdot e_0^{-1} \pmod Q$$
- Kiểm tra tính đúng đắn: $G^x \equiv Y \pmod P$.

---

## 3. Khai thác & Giả mạo chữ ký (Forgery)

Sau khi có khóa bí mật $x$, ta tự sinh chữ ký cho thông điệp mục tiêu $M = \text{b"give\_me\_gift"}$:
1. Chọn nonce ngẫu nhiên $k_{\text{target}} \in [1, Q-1]$.
2. $R_{\text{target}} = G^{k_{\text{target}}} \pmod P$.
3. $e_{\text{target}} = \text{Hash}(M \parallel R_{\text{target}})$.
4. $s_{\text{target}} = (k_{\text{target}} + e_{\text{target}} \cdot x) \pmod Q$.
5. Gửi lệnh `SUBMIT give_me_gift <R> <s>` lên server để nhận Flag.

Chi tiết cài đặt thuật toán LLL & CVP số học chính xác cao bằng `gmpy2` nằm trong tệp [solve.py](./solve.py).
