# eyes-desktop

Con mắt ASCII trên [profile GitHub của hdnng](https://github.com/hdnng/hdnng), làm thành hình nền động cho Ubuntu. Mắt **nhìn theo con trỏ chuột thật**.

- Chuột di chuyển: mống mắt liếc theo, con ngươi co lại khi chuột lại gần và giãn ra khi chuột ở xa. Khi chuột nằm ngay trên mắt thì mắt nheo lại.
- Chuột đứng yên (mặc định 8 giây): mắt quay về đúng "kịch bản" của profile card, gồm liếc sang, đọc từng dòng, nheo, chớp.
- Chớp mắt ngẫu nhiên, thỉnh thoảng chớp hai lần, và chớp khi liếc một khoảng xa.
- Tự co giãn theo độ phân giải màn hình: ASCII art được vẽ lại từ `assets/eye.json` nên luôn nét, kể cả ở 2K hay 4K. Nếu cắm thêm màn hình hoặc đổi độ phân giải, mắt tự căn lại.
- Có theme tối và sáng, dùng cùng bảng màu với profile card.

Không dùng trình duyệt và không sửa cấu hình hệ thống. Chỉ có một script Python và một file autostart trong thư mục home.

## Yêu cầu

- Ubuntu với phiên **X11** ("Ubuntu on Xorg", chọn ở góc dưới màn hình đăng nhập). Trên Wayland, mắt vẫn chạy nhưng chỉ thấy chuột khi chuột nằm trên cửa sổ X, nên phần lớn thời gian sẽ chạy kịch bản tự động.
- Các gói Python (chỉ cần cài một lần):

```bash
sudo apt install python3-tk python3-pil python3-pil.imagetk python3-xlib
```

## Chạy thử

```bash
python3 eyes.py --window
```

Lệnh này mở một cửa sổ 1280x720 bình thường để xem thử. Nhấn **Esc** để thoát.

## Đặt làm hình nền và tự chạy khi đăng nhập

```bash
./install.sh
```

Script ghi file `~/.config/autostart/eyes-desktop.desktop` và bật hình nền ngay.

```bash
./stop.sh        # tắt
./start.sh       # bật lại
./uninstall.sh   # tắt và bỏ tự chạy
```

Log nằm ở `~/.cache/eyes-desktop.log`.

## Tuỳ chỉnh

Sửa `config.json` rồi chạy lại `./start.sh`:

| Khoá | Ý nghĩa | Mặc định |
|---|---|---|
| `theme` | `"dark"` hoặc `"light"` | `"dark"` |
| `size` | chiều cao của mắt so với chiều cao màn hình | `0.6` |
| `position` | tâm mắt, tính theo tỉ lệ màn hình `[x, y]` | `[0.5, 0.5]` |
| `monitor` | `"primary"` hoặc số thứ tự màn hình (`0`, `1`…) | `"primary"` |
| `fps` | số khung hình mỗi giây | `30` |
| `idle_after` | số giây chuột đứng yên trước khi chạy kịch bản tự động | `8.0` |
| `background` | màu nền riêng, ví dụ `"#000000"` | theo theme |
| `font` | đường dẫn font monospace khác | DejaVu Sans Mono Bold |

Có thể ghi đè tạm qua dòng lệnh, ví dụ `./start.sh --theme light --size 0.5`.

## Cách hoạt động

- `assets/eye.json` được lấy từ `hdnng/hdnng` (sinh bởi `scripts/make_eye.py` ở repo đó). File chứa các lớp ASCII: nền tĩnh, mống mắt, con ngươi, vệt phản quang, 7 khung mí mắt, và đường viền khe mắt.
- Khi khởi động, `eyes.py` vẽ các lớp này bằng Pillow theo tỉ lệ vừa với màn hình.
- Mỗi khung hình chỉ dựng lại vùng quanh khe mắt (khoảng 1 ms), và chỉ khi có thay đổi nhìn thấy được. Mức CPU đo được khoảng 5–7% một nhân.
- Cửa sổ dùng kiểu `_NET_WM_WINDOW_TYPE_DESKTOP`, nên nằm dưới mọi ứng dụng như hình nền thật.
- Vị trí chuột lấy qua Xlib (`query_pointer`).

## Lưu ý

- Trên GNOME có bật extension icon desktop (Desktop Icons NG), icon có thể bị cửa sổ mắt che hoặc che lên mắt, tuỳ thứ tự khởi động. Nếu icon bị mất, chạy lại `./start.sh` sau khi đăng nhập xong.
- Khi đang mở ứng dụng toàn màn hình, mắt vẫn tiếp tục chạy ở phía sau.
