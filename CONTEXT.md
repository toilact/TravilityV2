# Travility

Ứng dụng giúp người Việt lên kế hoạch du lịch trong nước: người dùng mô tả mong muốn, AI dựng lịch trình trên bản đồ và cùng người dùng chỉnh sửa.

## Language

**User** (Người dùng):
Người có tài khoản trong app; sở hữu các Trip của mình.
_Avoid_: Account, customer, member

**Traveler Profile** (Hồ sơ du lịch):
Preference, Pace và Travel Mode mặc định của một User, được chép vào mỗi Trip mới lúc tạo. Đổi Traveler Profile không làm thay đổi các Trip đã có.
_Avoid_: Settings, persona

**Destination** (Điểm đến):
Một thành phố hoặc vùng mà app có dữ liệu Place đầy đủ (vd. Đà Lạt, Đà Nẵng – Hội An). Mỗi Trip thuộc đúng một Destination.
_Avoid_: City, region, khu vực

**Trip** (Chuyến đi):
Mong muốn du lịch của người dùng — một Destination, số ngày (và ngày đi nếu có), Budget, Preference, Pace, Travel Mode. Thuộc về đúng một User và chỉ người đó thấy. Một Trip có nhiều phiên bản Itinerary.
_Avoid_: Plan, tour, request

**Itinerary** (Lịch trình):
Một phương án cụ thể, bất biến, do AI tạo cho một Trip. Mỗi lần chỉnh sửa sinh ra một phiên bản Itinerary mới; phiên bản cũ được giữ để quay lại.
_Avoid_: Schedule, plan, lịch

**Conflict** (Xung đột):
Một điểm Itinerary không đáp ứng được mong muốn của Trip — vượt Budget, Stop ngoài giờ mở cửa của Place, thiếu Tag bắt buộc, Stop ngoài trời vào ngày dự báo mưa. Itinerary vẫn được tạo, kèm danh sách Conflict và gợi ý khắc phục.
_Avoid_: Error, warning, violation

**Revision** (Chỉnh sửa):
Một yêu cầu thay đổi bằng lời của người dùng trên Itinerary hiện tại, tạo ra phiên bản Itinerary kế tiếp. Chỉ những Stop liên quan đến yêu cầu được phép thay đổi.
_Avoid_: Edit, update, regenerate

**Pinned Stop** (Stop đã ghim):
Stop người dùng đánh dấu giữ nguyên; không Revision nào được thay đổi hay xoá nó.
_Avoid_: Locked, favorite, starred

**Place** (Địa điểm):
Một nơi có thật do nhóm thu thập và kiểm chứng — quán ăn, điểm tham quan, cafe, chỗ ở… Tồn tại độc lập với mọi Itinerary; AI chỉ được chọn Place có sẵn, không được tự nghĩ ra.
_Avoid_: POI, location, spot, điểm

**Stop** (Điểm dừng):
Một lần ghé một Place trong một Itinerary, vào một ngày và khung giờ cụ thể. Cùng một Place có thể xuất hiện ở nhiều Stop.
_Avoid_: Visit, activity, item

**Suggestion** (Gợi ý):
Một Place được đề xuất nhưng chưa nằm trong Itinerary (vd. từ ảnh cảm hứng hay câu hỏi "quanh đây có gì"). Chỉ trở thành Stop khi người dùng chấp nhận, qua một Revision.
_Avoid_: Recommendation, candidate, result

**Inspiration Photo** (Ảnh cảm hứng):
Ảnh người dùng đưa vào để diễn tả kiểu nơi họ muốn tới; app tìm các Place có cùng không khí và trả về dưới dạng Suggestion.
_Avoid_: Upload, image query

**Stay** (Chỗ ở):
Việc lưu trú qua đêm tại một Place loại chỗ ở, gắn với một đêm của Itinerary; là điểm xuất phát và kết thúc của mỗi ngày. Không phải Stop.
_Avoid_: Hotel, booking, lodging

**Leg** (Chặng):
Quãng di chuyển giữa hai điểm liên tiếp trong cùng một ngày (Stay → Stop, Stop → Stop, Stop → Stay).
_Avoid_: Route, segment, trip

**Travel Mode** (Phương tiện):
Cách di chuyển chính của một Trip — xe máy thuê (mặc định) hoặc taxi/Grab. Leg quá ngắn luôn đi bộ bất kể Travel Mode.
_Avoid_: Transport, vehicle

**Pace** (Nhịp độ):
Mức dày đặc của mỗi ngày trong Trip — thong thả, vừa (mặc định) hoặc dày — quyết định số Stop và khung giờ hoạt động mỗi ngày.
_Avoid_: Intensity, tempo, mật độ

**Forecast** (Dự báo thời tiết):
Thời tiết dự kiến cho từng ngày của một Trip có ngày đi cụ thể. Trip không có ngày đi thì không có Forecast.
_Avoid_: Weather data

**Tag** (Nhãn):
Một đặc điểm thuộc bộ từ vựng cố định (vd. cafe-chill, an-chay, thien-nhien) gắn cho Place. Là ngôn ngữ chung giữa sở thích người dùng và dữ liệu Place.
_Avoid_: Category, label, vibe

**Preference** (Sở thích):
Những gì người dùng muốn hoặc không muốn trong một Trip, quy về ba nhóm Tag: bắt buộc, ưu tiên, tránh.
_Avoid_: Filter, taste, interest

**Reason** (Lý do chọn):
Lời giải thích vì sao một Stop được chọn, dẫn chiếu tới Preference/Tag mà Place đó đáp ứng.
_Avoid_: Explanation, note

**Budget** (Ngân sách):
Số tiền người dùng muốn chi cho một Trip, bao gồm ăn uống, vé tham quan, Stay và chi phí các Leg trong thành phố. Không bao gồm di chuyển liên tỉnh đến/rời thành phố.
_Avoid_: Chi phí, price, cost (cost là số ước tính của Itinerary, không phải Budget)
