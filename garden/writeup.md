# Writeup: Garden

- **Category:** Web Exploitation
- **Difficulty:** Medium
- **Target:** Web application (Flask / SQLite / cshogi)

---

## 1. Tổng quan đề bài

Đề bài cung cấp dịch vụ web chơi cờ tướng Nhật Bản (Shogi) được viết bằng Flask, lưu trữ các nước đi cờ trong cơ sở dữ liệu SQLite (`shogi.db`). Flag của thử thách được chèn sẵn vào bảng `game_moves` dưới tên người dùng `admin`.

---

## 2. Phân tích mã nguồn & Lỗ hổng

### 2.1. Hardcoded Secret Key
Trong [main.py](./static/main.py):
```python
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
```
Nếu server triển khai không ghi đè biến môi trường, khóa ký session mặc định là `'dev-secret-key-change-in-production'`. Kẻ tấn công có thể giả mạo cookie `session` bằng `itsdangerous` / `SecureCookieSessionInterface`.

### 2.2. SQL Injection trong hàm lưu nước đi
Tại phương thức `save_move_to_db` ([main.py](./static/main.py#L85-L98)):
```python
cur.execute(f"""
    INSERT INTO game_moves (user_id, move, created_at)
    VALUES ('{self.user_id}', '{move_usi}', datetime('now'))
""")
```
Biến `self.user_id` lấy trực tiếp từ `session.get('user_id')` mà không qua lọc ký tự hay sử dụng Parameterized Query. Điều này dẫn đến lỗ hổng **SQL Injection**.

Tuy nhiên:
- Dữ liệu trả về ở các API `/game/state` chỉ nạp các nước đi hợp lệ theo chuẩn USI (`cshogi`) và cập nhật bàn cờ.
- Server không in trực tiếp kết quả SELECT tùy ý ra giao diện. Ta cần khai thác dưới dạng **Blind SQL Injection**.

---

## 3. Ý tưởng khai thác (Board-State Oracle)

Ta tạo một kênh Oracle 2 bước dựa vào trạng thái bàn cờ (SFEN):

1. **Bước 1 (Gửi payload injection):**
   Gửi cookie giả mạo với `user_id` có dạng:
   ```sql
   <rand_user>', (SELECT CASE WHEN (<CONDITION>) THEN '7g7f' ELSE json_extract('{', '$') END), datetime('now'))--
   ```
   - Nếu `<CONDITION>` là **TRUE**: Câu lệnh chèn nước đi `'7g7f'` (nước đi tốt mở đầu hợp lệ trong Shogi) cho người chơi `<rand_user>`.
   - Nếu `<CONDITION>` là **FALSE**: Hàm `json_extract('{', '$')` gặp lỗi cú pháp JSON không hợp lệ, khiến giao dịch `INSERT` thất bại hoàn toàn.

2. **Bước 2 (Kiểm tra trạng thái):**
   Gửi request `GET /game/state` với cookie sạch mang `user_id = <rand_user>`:
   - Nếu nước đi `7g7f` được lưu: Bàn cờ chuyển sang trạng thái mới (khác chuỗi SFEN mặc định ban đầu `lnsgkgsnl/...`). $\implies$ Điều kiện **TRUE**.
   - Nếu không có nước đi nào: Bàn cờ giữ nguyên trạng thái khởi tạo. $\implies$ Điều kiện **FALSE**.

3. **Bước 3 (Tìm kiếm nhị phân):**
   - Xác định độ dài flag: `length((SELECT move FROM game_moves WHERE user_id='admin' LIMIT 1)) >= mid`.
   - Dò từng ký tự: `unicode(substr((SELECT move FROM game_moves WHERE user_id='admin' LIMIT 1), {idx}, 1)) >= mid`.

---

## 4. Chạy kịch bản khai thác

Xem mã nguồn chi tiết tại [solve.py](./solve.py):
```bash
python solve.py http://<host>:<port> [optional_secret_key]
```
Kịch bản sẽ tự động xác thực Oracle, tính độ dài và in cờ ra màn hình.
