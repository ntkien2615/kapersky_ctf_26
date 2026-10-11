# Writeup: SudoKrypt

- **Category:** Cryptography
- **Difficulty:** Hard
- **Techniques:** Chosen-Plaintext Attack, Linear Recurrence Relations, GF(4093) Field Algebra, Vandermonde Systems, Custom Block Cipher Cryptanalysis

---

## 1. Tổng quan đề bài

Đề bài triển khai một dịch vụ mã hóa đối xứng tùy chỉnh mang tên **SudoKrypt**:
- Sử dụng mô hình mã hóa khối kết hợp ma trận bảng Sudoku / trường hữu hạn $\mathbb{F}_{16}$ cùng bộ tạo giả ngẫu nhiên dòng (SpectrumGenerator) trên trường $\text{GF}(4093)$.
- Server cho phép mã hóa tối đa 96 khối bản rõ tự chọn (Chosen-Plaintext), sau đó thực hiện thao tác biến đổi nội tại (`fold_for_flag()`) và trả về các khối bản mã của Flag bí mật.

---

## 2. Phân tích mật mã (Cryptanalysis)

Hệ thống bảo mật phụ thuộc vào hai thành phần chính:
1. **Lớp xáo trộn khối (Inner Block / S-box / Latin Square):** Kết hợp phép xoay khối `block_rotation`, hoán vị `q_perm` và bảng tra S-box trên 16 lanes.
2. **Bộ sinh PRNG (SpectrumGenerator):** Trạng thái sinh bởi:
   $$V[t][l] = \sum_{j=0}^{55} c_{l,j} \cdot n_j^t \pmod{4093}$$
   với 56 nút phổ (spectrum nodes) $n_j \in \text{GF}(4093)$ và các hệ số ban đầu $c_{l,j}$.

---

## 3. Các bước tấn công đại số 100% tất định (Deterministic Attack)

### 3.1. Phục hồi hoán vị và khử độ lệch xoay (Rotation Ambiguity)
- **Truy vấn 0..15:** Gửi các khối với byte đồng nhất $[(k \ll 4) \mid k] \times 16$. Nibble cao của mỗi từ giải mã trực tiếp ra $q_{\text{perm}}[k]$, từ đó khôi phục hoàn chỉnh $q_{\text{perm}}$ và $q_{\text{inv}}$.
- **Truy vấn 16..95:** Gửi byte có cấu trúc nhãn riêng biệt $[(i \ll 4) \mid i]_{i=0}^{15}$. Nhờ nhãn riêng biệt của từng lane, nibble cao của `words[0]` phản ánh trực tiếp phép quay:
  $$\text{rotation} = q_{\text{inv}}[\text{words}[0] \gg 12]$$
  Triệt tiêu hoàn toàn tính bất định về góc xoay mà không cần thử brute-force.

### 3.2. Bóc tách giá trị luồng PRNG (Stream Values)
Sử dụng tính khả nghịch của S-box và mối quan hệ trên trường hữu hạn:
$$sbox\_low = 11 \cdot (2 \cdot row\_field - col\_field + C) \bmod 16$$
Mỗi từ mã hóa ánh xạ đơn ánh về một giá trị luồng tương ứng. Duy nhất giá trị $C$ đúng sẽ thỏa mãn điều kiện `block_rotation` trên tất cả các khối.

### 3.3. Khôi phục đa thức truy hồi trên $\text{GF}(4093)$
Dãy PRNG $V[t][l]$ là tổ hợp tuyến tính của 56 lũy thừa $n_j^t$, do đó nó thỏa mãn một hệ thức truy hồi tuyến tính bậc 56:
$$V[t+56][l] + a_1 V[t+55][l] + \dots + a_{56} V[t][l] \equiv 0 \pmod{4093}$$
- Cả 16 lanes đều dùng chung đa thức đặc trưng:
  $$P(x) = x^{56} + a_1 x^{55} + \dots + a_{56}$$
- Qua 80 khối quan sát trên 16 lanes, ta thu được $24 \times 16 = 384$ phương trình cho 56 ẩn số.
- Giải hệ phương trình tuyến tính bằng phép khử Gauss trên $\text{GF}(4093)$ để tìm các hệ số $a_i$.
- Nghiệm của phương trình $P(x) = 0$ trên $\text{GF}(4093)$ chính là 56 nút phổ $n_j$.

### 3.4. Giải hệ Vandermonde & Giải mã Flag
- Thiết lập hệ ma trận Vandermonde $V_{t, j} = n_j^t \pmod{4093}$ và giải ra toàn bộ $16 \times 56$ hệ số ban đầu $c_{l,j}$.
- Tái tạo trạng thái PRNG ban đầu và tiến bộ sinh tới bước thứ 96.
- Thực thi `recon_prng.fold_for_flag()` tương tự server.
- Sử dụng các giá trị PRNG và hoán vị đã khôi phục để giải mã tuần tự từng khối bản mã của Flag và giải padding PKCS#7.

Mã nguồn khai thác chi tiết nằm trong [solve.py](./solve.py).
