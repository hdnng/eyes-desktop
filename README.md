# eyes-desktop

Hình nền động ASCII cho Ubuntu, dựng từ [profile GitHub của hdnng](https://github.com/hdnng/hdnng). Có hai cảnh:

- **`face`** (mặc định): avatar GitHub được vẽ lại bằng ký tự ASCII ở mật độ cao, phủ kín toàn màn hình, và có các hiệu ứng tương tác.
- **`eye`**: con mắt ASCII của profile card, như phiên bản đầu.

Không dùng trình duyệt và không sửa cấu hình hệ thống. Chỉ có script Python và một file autostart trong thư mục home.

## Cảnh `face`: hiệu ứng

| Hiệu ứng | Mô tả |
|---|---|
| Toàn màn hình | Ảnh được phóng phủ kín màn hình (kiểu "fill" của hình nền), cắt bớt trên dưới nhưng giữ tóc, hai mắt và mũi. Tự thích ứng với 16:9, 16:10, 21:9, nhiều màn hình và mọi độ phân giải. |
| Mắt nhìn theo chuột | Mỗi nhãn cầu được vẽ lại chi tiết. Mống mắt dựng từ chính mống mắt trong tranh, thêm vân sợi, vòng collarette và viền tối, tô màu xanh ngọc. Có đốm phản quang trễ hơn mống mắt một chút, lòng trắng có bóng đổ dưới mí. Mống mắt trượt **ra sau mí thật** khi liếc lên xuống, và **dẹt lại** khi liếc ra góc như nhãn cầu tròn. Hai mắt tính góc riêng nên có độ hội tụ. |
| Con ngươi | Co lại khi chuột lại gần, giãn ra khi chuột ở xa. |
| Mí mắt | Chớp ngẫu nhiên (thỉnh thoảng chớp hai lần), chớp khi liếc xa, nheo khi chuột đặt ngay trên mắt, và hạ xuống khi mắt nhìn xuống. Khi hạ, mí mang màu da và kéo theo hàng mi ở mép dưới. |
| Tóc | Các sợi lay theo đúng hướng mọc: đuôi tóc bay nhiều hơn chân tóc, có sóng chạy dọc sợi và gió thổi từng đợt. **Rê chuột qua tóc** sẽ hất tóc theo hướng chuột, rồi tóc bật về chỗ cũ. |
| Mặt nước | Lăn tăn sóng. **Click** vào đâu là vòng gợn lan ra từ đó; rê chuột trên mặt nước để lại vệt sóng. |
| Đốm sáng | Các đốm trắng trên tóc lấp lánh. |
| Ánh sáng theo chuột | Vùng sáng dịu đi theo con trỏ, làm ký tự dày và sáng hơn. |
| Khi chuột đứng yên | Sau 8 giây, mắt chạy lại "kịch bản" của profile card: liếc sang, đọc từng dòng, nheo, chớp. |

Cách hoạt động:

- Mỗi khung hình, avatar (đã phóng to 2 lần và làm nét) được lấy mẫu lại qua một trường biến dạng (tóc, nước, gợn sóng), còn hai mắt thì được vẽ lại hoàn toàn. Kết quả được chuyển thành ký tự.
- Mỗi ô chữ chia thành 2×3 ô con. Ký tự được chọn theo cả độ đậm lẫn hình dạng đo từ font thật, nên các nét như mi mắt hay sợi tóc vẫn giữ được hướng.
- Hình được vẽ thẳng lên cửa sổ bằng `libX11` (`XPutImage`), mỗi khung hình chỉ gửi những vùng có thay đổi. Nếu máy không hỗ trợ, chương trình tự chuyển sang vẽ bằng Tk.

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
| `fit` | cảnh face: `"cover"` phủ kín màn hình, `"contain"` hiện cả ảnh vuông ở giữa | `"cover"` |
| `focus` | cảnh face, kiểu `cover`: điểm của ảnh được đặt vào giữa màn hình, `[x, y]` từ 0 đến 1. Tăng `y` để thấy nhiều mũi và mặt nước hơn, giảm để thấy nhiều tóc hơn | `[0.5, 0.5]` |
| `cell` | cảnh face: độ rộng một ký tự (px, tính ở 1080p). Nhỏ hơn thì chi tiết hơn và tốn CPU hơn. Tự nhân theo độ phân giải | `5` |
| `hair_strength` | biên độ tóc bay (px của avatar) | `3.5` |
| `face_size` | cảnh face, kiểu `contain`: cạnh ảnh so với chiều cao màn hình | `0.92` |
| `size` | cảnh eye: chiều cao con mắt so với màn hình | `0.6` |
| `position` | kiểu `contain` và cảnh eye: tâm hình, `[x, y]` | `[0.5, 0.5]` |
| `monitor` | `"primary"` hoặc số thứ tự màn hình | `"primary"` |
| `fps` | khung hình/giây cho mắt và tương tác | `24` |
| `ambient_fps` | khung hình/giây cho tóc và nước (tự lên ít nhất 20 khi có gợn sóng) | `12` |
| `idle_after` | số giây chuột đứng yên trước khi chạy kịch bản tự động | `8.0` |
| `effects` | bật/tắt từng hiệu ứng: `water`, `ripples`, `hair`, `stars`, `glow` | tất cả bật |
| `background` | màu nền riêng, ví dụ `"#000000"` | theo theme |
| `font` | đường dẫn font monospace khác | DejaVu Sans Mono Bold |

Có thể ghi đè tạm qua dòng lệnh, ví dụ `./start.sh --theme light --cell 4`.

## CPU

Số đo trên máy thử ở 1080p, cảnh face phủ kín màn hình, tính theo phần trăm một nhân CPU:

| Trạng thái | CPU |
|---|---|
| Đủ hiệu ứng, chuột đứng yên | khoảng 18% |
| Đủ hiệu ứng, đang rê chuột qua tóc | khoảng 23% |
| Chỉ có mắt (`hair` và `water` tắt) | khoảng 7% |
| Cửa sổ đang dùng được phóng to hoặc toàn màn hình | khoảng 0% (tự tạm dừng) |

Tóc chiếm phần lớn chi phí. Muốn nhẹ hơn, giảm `ambient_fps` (ví dụ 8), tăng `cell` (ví dụ 6), hoặc tắt `hair`. Ánh sáng theo chuột và vệt sóng chỉ chạy khi con trỏ nằm trên chính hình nền.

## Cấu trúc

| File | Nội dung |
|---|---|
| `eyes.py` | cửa sổ hình nền, đọc chuột, theo dõi màn hình, tạm dừng khi bị che |
| `behaviour.py` | hướng nhìn, con ngươi, chớp mắt, kịch bản lúc chuột đứng yên (lấy từ `build_card.py` của repo profile) |
| `scene_face.py` | cảnh face: bố cục toàn màn hình, vẽ nhãn cầu, tóc, nước, gợn sóng, ánh sáng, đốm sáng |
| `scene_eye.py` | cảnh eye |
| `ascii_render.py` | chuyển ảnh sang ASCII bằng numpy; vẽ thẳng lên cửa sổ bằng libX11 (hoặc ảnh Tk nếu không được), chỉ vẽ lại vùng thay đổi |
| `assets/avatar.png` | avatar GitHub (ảnh xám) |
| `assets/face.json` | đường mí trên, mí dưới, mống mắt và độ dày hàng mi của từng mắt; các vùng tóc và hướng sợi; đường mặt nước; tất cả tính theo pixel của avatar |
| `assets/eye.json` | con mắt ASCII từ `hdnng/hdnng` |

Muốn dùng ảnh khác, thay `assets/avatar.png` (ảnh vuông) và sửa toạ độ trong `assets/face.json` cho khớp. Đường mí được đo theo từng điểm (x, y) dọc mép trên và mép dưới của khe mắt.

## Lưu ý

- Trên GNOME có bật extension icon desktop (Desktop Icons NG), icon có thể bị hình nền che hoặc che lên hình nền, tuỳ thứ tự khởi động. Nếu icon bị mất, chạy lại `./start.sh` sau khi đăng nhập xong.
- Click tạo gợn sóng chỉ hoạt động khi click trúng vùng hình nền trống. Nếu extension icon desktop nằm phía trên và nhận click thay, gợn sóng sẽ không xuất hiện, nhưng các hiệu ứng khác vẫn chạy.
