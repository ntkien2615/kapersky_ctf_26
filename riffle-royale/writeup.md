# Writeup: Riffle Royale

- **Category:** Cryptography
- **Difficulty:** Hard
- **Techniques:** Elliptic Curve Parameter Reconstruction, Algebraic Resultants, Greatest Common Divisor (GCD), Point Scalar Multiplication

---

## 1. Tổng quan đề bài

Thử thách là một trò chơi cờ bạc ("Riffle Royale") chạy trên nền web:
- Server sinh một đường cong Elliptic ngẫu nhiên $y^2 = x^3 + ax + b \pmod p$ với số nguyên tố $p \approx 2^{255}$.
- Chọn một điểm bước nhảy $S$ và hai điểm xuất phát $U, V$.
- Sinh 2 quỹ đạo hoành độ (lane 0 và lane 1) độ dài 7:
  - Lane 0: $x(U), x(U+S), x(U+2S), \dots, x(U+6S)$
  - Lane 1: $x(V), x(V+S), x(V+2S), \dots, x(V+6S)$
- Trộn lẫn ngẫu nhiên (Riffle Shuffle) hai dãy này thành 14 số nguyên gửi cho client (`samples`).
- **Nhiệm vụ:** Dự đoán hoành độ tại bước nhảy mục tiêu $T = 2^{32} + 1609$, tức là $x(U + T \cdot S)$.

---

## 2. Phân tích toán học & Lỗ hổng

### 2.1. Quan hệ đại số giữa 3 hoành độ liên tiếp
Cho 3 điểm liên tiếp $P_{i-1}, P_i, P_{i+1}$ thỏa mãn $P_{i+1} = P_i + S$ và $P_i = P_{i-1} + S$ trên đường cong Weierstrass. Ta có công thức cộng điểm đối với hoành độ:
$$(x_{i+1} + x_{i-1})(x_i - x_S)^2 = 2(x_i + x_S)(x_i x_S + a) + 4b$$
Triệt tiêu $y$ và nhóm lại theo bậc của hoành độ bước nhảy $x_S$:
$$A_i x_S^2 + B_i x_S + C_i \equiv 2(x_i - x_{i+1})a + 4b \pmod p$$
với:
- $A_i = x_{i+1} - 2x_i + x_{i-1}$
- $B_i = -2x_i(x_{i+1} + x_i + x_{i-1})$
- $C_i = x_i^2(x_{i+1} + x_{i-1})$

### 2.2. Khử tham số $(a, b)$ và đa thức Resultant
Trừ các phương trình của các chỉ số $i_1, i_2, i_3$ khác nhau, ta triệt tiêu hoàn toàn hệ số $a$ và $b$, thu được đa thức bậc hai ẩn $x_S$:
$$Q(x_S) = \alpha x_S^2 + \beta x_S + \gamma \equiv 0 \pmod p$$
Khi có ít nhất 3 đa thức $Q_1, Q_2, Q_3$, chúng cùng nhận nghiệm $x_S \pmod p$. Khi đó:
$$\text{Resultant}(Q_1, Q_2) \equiv 0 \pmod p \quad \text{và} \quad \text{Resultant}(Q_2, Q_3) \equiv 0 \pmod p$$
Nói cách khác, trên tập số nguyên $\mathbb{Z}$:
$$p \mid \gcd\Big(\text{Resultant}(Q_1, Q_2),\, \text{Resultant}(Q_2, Q_3)\Big)$$

---

## 3. Quá trình giải (Attack Pipeline)

1. **Phân tách 2 dãy (Demultiplexing):**
   Trong 14 mẫu quan sát, phần tử đầu tiên chắc chắn thuộc một dãy. Ta thử tất cả các tổ hợp $\binom{13}{6} = 1716$ khả năng chọn 6 phần tử còn lại để tạo thành dãy 7 điểm của lane 0.

2. **Tìm số nguyên tố $p$:**
   Với mỗi tổ hợp, tính GCD của các đa thức resultant. Nếu $\gcd > 2^{200}$, loại bỏ các ước số nguyên tố nhỏ ($< 10000$), giá trị còn lại chính là modulo nguyên tố bí mật $p$.

3. **Khôi phục tham số đường cong:**
   - Từ các hệ số của $Q_1, Q_2 \pmod p$, giải nghiệm duy nhất của $x_S$.
   - Thế $x_S$ ngược lại để tìm các hệ số $a$ và $b$.
   - Tính tung độ $y_S, y_0$ bằng căn bậc hai modulo $p$: $y = (x^3 + ax + b)^{(p+1)/4} \pmod p$.

4. **Tính điểm đích và nộp Flag:**
   - Dùng thuật toán nhân điểm nhanh (Double-and-Add) tính $T \cdot S$ với $T = 2^{32} + 1609$.
   - Tính điểm đích: $P_{\text{target}} = U + (T \cdot S)$.
   - Gửi $x(P_{\text{target}})$ qua API `/api/submit` để nhận Flag.

Mã nguồn khai thác chi tiết nằm trong [solve.py](./solve.py).
