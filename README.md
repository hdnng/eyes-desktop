# eyes-desktop

Hình nền động ASCII cho Ubuntu, dựng từ [profile GitHub của hdnng](https://github.com/hdnng/hdnng). Có hai cảnh:

- **`face`** (mặc định): avatar GitHub được vẽ lại bằng ký tự ASCII ở mật độ cao và có các hiệu ứng tương tác.
- **`eye`**: con mắt ASCII của profile card, như phiên bản đầu.

Không dùng trình duyệt và không sửa cấu hình hệ thống. Chỉ có script Python và một file autostart trong thư mục home.

## Cảnh `face`: hiệu ứng

| Hiệu ứng | Mô tả |
|---|---|
| Mắt nhìn theo chuột | Cả hai mắt liếc theo con trỏ, mỗi mắt tính góc riêng nên có độ hội tụ như mắt thật. Mống mắt được tô màu xanh ngọc. |
| Con ngươi | Co lại khi chuột lại gần, giãn ra khi chuột ở xa. |
| Mí mắt | Chớp ngẫu nhiên, thỉnh thoảng chớp hai lần, và chớp khi liếc một khoảng xa. Nheo lại khi chuột đặt ngay trên mắt. Khi mí hạ xuống có viền mi tối chạy theo. |
| Mặt nước | Nửa dưới lăn tăn sóng. **Click** vào đâu là vòng gợn lan ra từ đó; rê chuột trên mặt nước để lại vệt sóng nhỏ. |
| Tóc | Lay nhẹ. |
| Đốm sáng | Các đốm trắng trên tóc lấp lánh. |
| Ánh sáng theo chuột | Một vùng sáng dịu đi theo con trỏ trên khuôn mặt, làm ký tự dày và sáng hơn. |
| Khi chuột đứng yên | Sau 8 giây, mắt chạy lại đúng "kịch bản" của profile card: liếc sang, đọc từng dòng, nheo, chớp. |

Cách hoạt động:

- Mỗi khung hình, avatar được lấy mẫu lại qua một trường biến dạng (mắt, nước, tóc) rồi chuyển thành ký tự.
- Mỗi ô chữ được chia thành 2×3 ô con. Ký tự được chọn theo cả độ đậm lẫn hình dạng đo từ font thật, nên các nét như mi mắt hay sợi tóc vẫn giữ được hướng.
- Mắt chuyển động bằng cách "uốn" phần ảnh bên trong khe mắt, nên vẫn là nét vẽ gốc của avatar chứ không phải hình vẽ thêm.

## Yêu cầu

- Ubuntu với phiên **X11** ("Ubuntu on Xorg", chọn ở biểu tượng bánh răng trên màn hình đăng nhập). Trên Wayland, chương trình vẫn chạy nhưng chỉ thấy chuột khi chuột nằm trên cửa sổ X, nên phần lớn thời gian mắt sẽ chạy kịch bản tự động.
- Các gói Python, chỉ cần cài một lần:

```bash
sudo apt install python3-tk python3-pil python3-pil.imagetk python3-xlib python3-numpy
```

## Chạy thử

```bash
python3 eyes.py --window
```

Lệnh này mở cửa sổ 1280x720 để xem thử. Nhấn **Esc** để thoát. Thêm `--scene eye` để xem cảnh con mắt.

## Đặt làm hình nền và tự chạy khi đăng nhập

```bash
./install.sh
```

```bash
./stop.sh        # tắt
./start.sh       # bật lại (sau khi sửa config.json)
./uninstall.sh   # tắt và bỏ tự chạy
```

Log nằm ở `~/.cache/eyes-desktop.log`.

## Tuỳ chỉnh (`config.json`)

| Khoá | Ý nghĩa | Mặc định |
|---|---|---|
| `scene` | `"face"` hoặc `"eye"` | `"face"` |
| `theme` | `"dark"` hoặc `"light"` | `"dark"` |
| `face_size` | cảnh face: cạnh khuôn mặt so với chiều cao màn hình | `0.92` |
| `cell` | cảnh face: độ rộng một ký tự (px, tính ở 1080p). Nhỏ hơn thì chi tiết hơn và tốn CPU hơn. Tự nhân theo độ phân giải, ví dụ ở 4K thì 5 thành 10 | `5` |
| `size` | cảnh eye: chiều cao con mắt so với màn hình | `0.6` |
| `position` | tâm hình, theo tỉ lệ màn hình `[x, y]` | `[0.5, 0.5]` |
| `monitor` | `"primary"` hoặc số thứ tự màn hình | `"primary"` |
| `fps` | khung hình/giây cho mắt và tương tác | `24` |
| `ambient_fps` | tốc độ cập nhật nước và tóc (tự lên 20 khi đang có gợn sóng) | `6` |
| `idle_after` | số giây chuột đứng yên trước khi chạy kịch bản tự động | `8.0` |
| `effects` | bật/tắt từng hiệu ứng: `water`, `ripples`, `hair`, `stars`, `glow` | tất cả bật |
| `background` | màu nền riêng, ví dụ `"#000000"` | theo theme |
| `font` | đường dẫn font monospace khác | DejaVu Sans Mono Bold |

Có thể ghi đè tạm qua dòng lệnh, ví dụ `./start.sh --theme light --cell 4`.

## CPU

Số đo trên máy thử ở 1080p, tính theo phần trăm một nhân CPU:

| Trạng thái | CPU |
|---|---|
| Cảnh face, đủ hiệu ứng | khoảng 15–20% |
| Cảnh face, chỉ có mắt (`water`, `hair`, `stars` tắt) | khoảng 9% |
| Cảnh eye | khoảng 5–7% |
| Cửa sổ đang dùng được phóng to hoặc toàn màn hình | khoảng 0% (tự tạm dừng) |

Ánh sáng theo chuột và vệt sóng chỉ chạy khi con trỏ nằm trên chính hình nền, không chạy khi con trỏ nằm trên cửa sổ ứng dụng. Muốn nhẹ hơn nữa, tắt `hair` hoặc `water`, hoặc giảm `ambient_fps`.

## Cấu trúc

| File | Nội dung |
|---|---|
| `eyes.py` | cửa sổ hình nền, đọc chuột, theo dõi màn hình, tạm dừng khi bị che |
| `behaviour.py` | hướng nhìn, con ngươi, chớp mắt, kịch bản lúc chuột đứng yên (lấy từ `build_card.py` của repo profile) |
| `scene_face.py` | cảnh face: biến dạng mắt, nước, tóc, gợn sóng, ánh sáng, đốm sáng |
| `scene_eye.py` | cảnh eye |
| `ascii_render.py` | chuyển ảnh sang ASCII bằng numpy, vẽ theo ô và chỉ vẽ lại ô thay đổi |
| `assets/avatar.png` | avatar GitHub (ảnh xám) |
| `assets/face.json` | vị trí hai mắt (elip, mống mắt), đường mặt nước, vùng tóc, tính theo pixel của avatar |
| `assets/eye.json` | con mắt ASCII từ `hdnng/hdnng` |

Muốn dùng ảnh khác, thay `assets/avatar.png` (ảnh vuông) và sửa toạ độ trong `assets/face.json` cho khớp.

## Lưu ý

- Trên GNOME có bật extension icon desktop (Desktop Icons NG), icon có thể bị hình nền che hoặc che lên hình nền, tuỳ thứ tự khởi động. Nếu icon bị mất, chạy lại `./start.sh` sau khi đăng nhập xong.
- Click tạo gợn sóng chỉ hoạt động khi click trúng vùng hình nền trống. Nếu extension icon desktop nằm phía trên và nhận click thay, gợn sóng sẽ không xuất hiện, nhưng các hiệu ứng khác vẫn chạy.
