"""
services/storyline_engine.py
─────────────────────────────────────────────────────────────────────────────
Hệ thống Kịch bản Mùa giải Đột phá (Esports Dynamic Storylines) cho Sim_Val.

Cung cấp:
1. Kho 14 Kịch bản Archetype kinh điển của Esports (Vô địch, Lọ Lem, Đại gia Ả Rập, Super Team, Nerf Riot...).
2. Ma trận lọc điều kiện (Context-Aware Eligibility) & Thiên kiến Khu vực (Regional Biases).
3. Máy tự động bốc thăm dự thảo kịch bản mùa mới (Draft Generation).
4. Áp dụng chốt kịch bản vào Database & Cập nhật CampaignClubState (Commit Storylines).
"""

import json
import random
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from models import db, Campaign, CampaignClubState, CampaignSeason, CampaignStagePlacement, CampaignStoryline, Club, Region


# ─────────────────────────────────────────────────────────────────────────────
# 1. KHO 14 KỊCH BẢN ARCHETYPE (SCENARIO CATALOG)
# ─────────────────────────────────────────────────────────────────────────────

SCENARIO_CATALOG: Dict[str, Dict[str, Any]] = {
    'SC_CHAMP_CURSE': {
        'key': 'SC_CHAMP_CURSE',
        'title': 'Lời Nguyền Nhà Vô Địch',
        'badge': '👑 Lời Nguyền Vô Địch',
        'badge_color': 'amber',
        'target_type': 'form',
        'default_impact': -20,
        'impact_range': (-25, -15),
        'headlines': [
            "ÁC MỘNG BẢO VỆ NGÔI VƯƠNG: {club} bắt đầu mùa giải mới dưới áp lực nghẹt thở của Lời nguyền Vô địch!",
            "KIỆT SỨC TRÊN ĐỈNH CAO: {club} bị các đối thủ mổ băng chiến thuật, khởi đầu chật vật!",
            "CÁI BÓNG CỦA NHÀ VUA: Liệu {club} có phá vỡ dớp sa sút phong độ sau khi nâng cúp danh giá?"
        ],
        'descriptions': [
            "Sau khi chạm tay vào đỉnh cao vinh quang mùa trước, {club} bước vào năm mới với lịch trình ăn mừng, quảng cáo dày đặc và sự tự mãn âm ỉ. Mọi đội tuyển đều xem họ là 'con mồi' số một để nghiên cứu và khắc chế triệt để.",
        ],
        'regional_bias': {'americas': 1.0, 'pacific': 1.2, 'emea': 1.0, 'china': 1.5},
    },
    'SC_SUPER_TEAM': {
        'key': 'SC_SUPER_TEAM',
        'title': 'Super Team Triệu Đô',
        'badge': '💰 Super Team Triệu Đô',
        'badge_color': 'purple',
        'target_type': 'rating',
        'default_impact': 6,
        'impact_range': (4, 9),
        'target_rating_cap': 97,
        'headlines': [
            "BÃO CHUYỂN NHƯỢNG: {club} kích hoạt bom tấn triệu đô, gom dàn siêu sao quyết tâm phục thù!",
            "DẢI NGÂN HÀ {region}: {club} xây dựng 'Super Team' đáng sợ nhất lịch sử giải đấu!",
            "TẤT TAY CHO NGÔI VƯƠNG: Giới chủ {club} chi tiền không tiếc tay để biến đội hình thành cỗ máy hủy diệt!"
        ],
        'descriptions': [
            "Căm phẫn sau thất bại mùa trước, ban lãnh đạo {club} đã dốc cạn ngân sách để chiêu mộ những tay súng khét tiếng nhất. Sức mạnh đội hình được nâng lên mức thượng thừa, nhưng áp lực phải thắng đang đè nặng lên từng cá nhân.",
        ],
        'regional_bias': {'americas': 2.0, 'pacific': 0.8, 'emea': 1.2, 'china': 1.0},
    },
    'SC_OIL_TYCOON': {
        'key': 'SC_OIL_TYCOON',
        'title': 'Đại Gia Bơm Tiền Đổi Đời',
        'badge': '🛢️ Đại Gia Đổi Đời',
        'badge_color': 'emerald',
        'target_type': 'rating',
        'default_impact': 14,
        'impact_range': (10, 18),
        'headlines': [
            "CHẤN ĐỘNG TÀI CHÍNH: Tập đoàn Trung Đông thâu tóm {club}, rót vốn tái thiết toàn diện!",
            "ĐỔI ĐỜI SAU MỘT ĐÊM: {club} lột xác thành thế lực mới nhờ túi tiền không đáy của giới siêu giàu!",
            "GAMING HOUSE TRIỆU ĐÔ: {club} bất ngờ trở thành bến đỗ trong mơ với chế độ đãi ngộ kỷ lục!"
        ],
        'descriptions': [
            "Từng là đội bóng nhược tiểu thường xuyên đội sổ, {club} bất ngờ được một quỹ đầu tư tài phiệt mua lại. Với gaming house đỉnh cao, ban huấn luyện ngoại quốc và mức lương ngất ngưởng, {club} lập tức đe dọa trật tự cũ của {region}.",
        ],
        'regional_bias': {'americas': 0.8, 'pacific': 1.2, 'emea': 2.0, 'china': 0.8},
    },
    'SC_FIRE_SALE': {
        'key': 'SC_FIRE_SALE',
        'title': 'Khủng Hoảng Bán Máu',
        'badge': '📉 Bán Máu / Khủng Hoảng',
        'badge_color': 'red',
        'target_type': 'rating',
        'default_impact': -14,
        'impact_range': (-18, -10),
        'headlines': [
            "KHỦNG HOẢNG TÀI CHÍNH: {club} giải tán dàn sao chủ lực, buộc phải đôn lứa trẻ thi đấu!",
            "CHẢY MÁU CHẤT XÁM: {club} thắt lưng buộc bụng sau một năm kinh doanh thua lỗ nặng nề!",
            "TẬN CÙNG NỖI THẤT VỌNG: {club} chia tay trụ cột vì cạn kiệt ngân sách duy trì đội tuyển!"
        ],
        'descriptions': [
            "Khoản đầu tư mùa trước không đem lại danh hiệu khiến các nhà tài trợ đồng loạt tháo chạy khỏi {club}. Để tránh vỡ nợ, đội bóng buộc phải bán đi những ngôi sao sáng nhất và bước vào mùa giải mới với đội hình chắp vá.",
        ],
        'regional_bias': {'americas': 1.0, 'pacific': 1.0, 'emea': 1.2, 'china': 1.5},
    },
    'SC_CINDERELLA': {
        'key': 'SC_CINDERELLA',
        'title': 'Cổ Tích Ngựa Ô (Lọ Lem)',
        'badge': '🌟 Cổ Tích Ngựa Ô',
        'badge_color': 'sky',
        'target_type': 'form',
        'default_impact': 20,
        'impact_range': (15, 25),
        'headlines': [
            "CƠN ĐỊA CHẤN TỪ VỰC THẲM: Ngựa ô {club} thi đấu thăng hoa, quật ngã các ông lớn!",
            "CỔ TÍCH LỌ LEM {region}: Không ai đặt kỳ vọng, nhưng {club} đang viết nên câu chuyện kỳ diệu!",
            "KHÔNG CÒN GÌ ĐỂ MẤT: {club} khuấy đảo giải đấu bằng lối bắn rực lửa không biết sợ hãi!"
        ],
        'descriptions': [
            "Bị đánh giá là kẻ lót đường không có cửa tranh chấp, {club} bước vào mùa giải với tâm lý cởi bỏ hoàn toàn áp lực. Tinh thần gắn kết và lối đánh dị biệt giúp họ thi đấu bùng nổ như những chiến binh cảm tử.",
        ],
        'regional_bias': {'americas': 0.8, 'pacific': 1.8, 'emea': 1.0, 'china': 1.2},
    },
    'SC_SILVER_CURSE': {
        'key': 'SC_SILVER_CURSE',
        'title': 'Bóng Ma Vua Về Nhì',
        'badge': '🥈 Vua Về Nhì',
        'badge_color': 'slate',
        'target_type': 'form',
        'default_impact': -15,
        'impact_range': (-20, -10),
        'headlines': [
            "BÓNG MA TÂM LÝ: {club} bước vào mùa mới với nỗi ám ảnh gục ngã trước ngưỡng cửa thiên đường!",
            "LIỆU CÓ THOÁT ĐƯỢC DỚP? {club} đối mặt áp lực cực lớn ở các trận cầu sinh tử!",
            "KẺ VỀ NHÌ VĨNH CỬU: {club} áp đảo vòng ngoài nhưng liệu có vượt qua rào cản tinh thần ở trận chung kết?"
        ],
        'descriptions': [
            "Nhiều lần lọt vào trận chung kết nhưng luôn thất bại ở những hiệp đấu cuối cùng, {club} đang mang trong mình vết thương tâm lý sâu sắc. Họ chơi rất hay trước các đội nhỏ nhưng hễ bước vào thời khắc quyết định là dễ bị 'cóng tay'.",
        ],
        'regional_bias': {'americas': 1.0, 'pacific': 1.2, 'emea': 1.5, 'china': 0.8},
    },
    'SC_REVENGE_SQUAD': {
        'key': 'SC_REVENGE_SQUAD',
        'title': 'Băng Cướp Báo Thù',
        'badge': '⚔️ Băng Cướp Báo Thù',
        'badge_color': 'rose',
        'target_type': 'form',
        'default_impact': 18,
        'impact_range': (12, 22),
        'headlines': [
            "LỬA HẬN ĐỐT CHÁY META: Đội hình 'phế phẩm' của {club} quyết tâm chứng minh các ông lớn đã sai lầm!",
            "BĂNG CƯỚP HOÀN LƯƠNG: {club} tập hợp những kẻ bị thải loại và sẵn sàng trả thù cả giải đấu!",
            "CHỨNG MINH BẢN THÂN: Dàn tuyển thủ {club} thi đấu bằng 200% ngọn lửa kiêu hãnh!"
        ],
        'descriptions': [
            "Đội hình của {club} quy tụ những tuyển thủ từng bị các tổ chức hàng đầu chê bai, đẩy lên băng ghế dự bị hoặc thanh lý không thương tiếc. Mang trong lòng khát khao phục thù cháy bỏng, họ thi đấu với tinh thần ăn tươi nuốt sống.",
        ],
        'regional_bias': {'americas': 1.5, 'pacific': 1.0, 'emea': 1.2, 'china': 0.8},
    },
    'SC_LAST_DANCE': {
        'key': 'SC_LAST_DANCE',
        'title': 'The Last Dance (Vũ Khúc Cuối)',
        'badge': '⏳ The Last Dance',
        'badge_color': 'amber',
        'target_type': 'form',
        'default_impact': 15,
        'impact_range': (10, 20),
        'headlines': [
            "VŨ KHÚC CUỐI CÙNG: Dàn cựu binh huyền thoại của {club} bước vào mùa giải chia tay sự nghiệp!",
            "CHÁY HẾT MÌNH LẦN CUỐI: {club} quyết tâm để lại dấu ấn trước khi thế hệ vàng giải nghệ!",
            "BẢN LĨNH LÃO TƯỚNG: Kinh nghiệm trận mạc của {club} biến họ thành mối hiểm họa chết người ở ván đấu sinh tử!"
        ],
        'descriptions': [
            "Các trụ cột của {club} đều đã bước sang sườn dốc bên kia của sự nghiệp và thống nhất đây sẽ là năm thi đấu cuối cùng trước khi giải nghệ. Dù phản xạ không còn như đôi mươi, sự gắn kết và độ già dơ của họ là vô đối.",
        ],
        'regional_bias': {'americas': 1.2, 'pacific': 1.5, 'emea': 1.2, 'china': 0.8},
    },
    'SC_RIOT_PATCH': {
        'key': 'SC_RIOT_PATCH',
        'title': 'Địa Chấn Bản Vá Riot',
        'badge': '🎯 Bão Nerf Riot',
        'badge_color': 'red',
        'target_type': 'form',
        'default_impact': -16,
        'impact_range': (-20, -12),
        'headlines': [
            "BÚA NERF GIÁNG XUỐNG: Bản cập nhật lớn của Riot đánh thẳng vào lối chơi tủ của {club}!",
            "SỐC META: {club} lúng túng điều chỉnh chiến thuật sau khi các đặc vụ quen thuộc bị suy yếu!",
            "CƠN ÁC MỘNG BẢN VÁ: Lối chơi của {club} không còn đất diễn, phong độ rơi tự do!"
        ],
        'descriptions': [
            "Riot Games tung ra bản cập nhật làm rung chuyển toàn bộ meta giải đấu. Phong cách thi đấu sở trường của {club} bị giảm sức mạnh nặng nề, buộc họ phải học lại bài vở từ đầu trong sự chật vật.",
        ],
        'regional_bias': {'americas': 1.0, 'pacific': 1.0, 'emea': 1.0, 'china': 1.5},
    },
    'SC_VISA_HELL': {
        'key': 'SC_VISA_HELL',
        'title': 'Địa Ngục Visa & Kỳ Tích Dự Bị',
        'badge': '✈️ Địa Ngục Visa',
        'badge_color': 'orange',
        'target_type': 'form',
        'default_impact': -12,
        'impact_range': (-18, 15), # Có xác suất nổ kỳ tích dương!
        'headlines': [
            "SỰ CỐ XUẤT CẢNH: {club} mất tuyển thủ chủ lực vì rắc rối Visa ngay trước thềm giải đấu!",
            "THỬ THÁCH NGHIỆT NGÃ: {club} phải đôn tuyển thủ streamer dự bị vào thi đấu khẩn cấp!",
            "BẤT NGỜ DỰ BỊ: Liệu {club} có biến thảm họa nhân sự thành một kỳ tích chấn động?"
        ],
        'descriptions': [
            "Ngôi sao gánh đội của {club} không kịp có thị thực để thi đấu quốc tế. Họ phải vội vã đưa một tuyển thủ dự bị vào trám chỗ. Áp lực khổng lồ có thể bẻ gãy đội bóng, nhưng cũng có thể biến kẻ đóng thế thành người hùng dân tộc.",
        ],
        'regional_bias': {'americas': 0.8, 'pacific': 2.0, 'emea': 0.8, 'china': 1.5},
    },
    'SC_TWITTER_BEEF': {
        'key': 'SC_TWITTER_BEEF',
        'title': 'Chiến Tranh Bàn Phím (Banter Beef)',
        'badge': '💬 Drama Bàn Phím',
        'badge_color': 'purple',
        'target_type': 'form',
        'default_impact': 12,
        'impact_range': (-12, 16),
        'headlines': [
            "ĐẠI CHIẾN MẠNG XÃ HỘI: {club} hâm nóng bầu không khí bằng những lời khiêu khích gay gắt!",
            "TÂM ĐIỂM DƯ LUẬN: Mọi ánh mắt đổ dồn về {club} sau màn khẩu chiến nảy lửa với đối thủ!",
            "GÁNH NẶNG PHÁT NGÔN: Tuyển thủ {club} tự đặt mình vào thế chân tường sau loạt phát biểu ngông cuồng!"
        ],
        'descriptions': [
            "Màn đấu võ mồm không khoan nhượng giữa các tuyển thủ {club} và đối thủ đã thu hút hàng triệu lượt xem trên Twitter/X. Giờ đây họ buộc phải chứng minh thực lực trên sàn đấu, hoặc trở thành trò cười cho toàn cõi mạng.",
        ],
        'regional_bias': {'americas': 2.2, 'pacific': 0.6, 'emea': 1.5, 'china': 0.5},
    },
    'SC_GOLDEN_YOUTH': {
        'key': 'SC_GOLDEN_YOUTH',
        'title': 'Thế Hệ Vàng Lò Trẻ Bùng Nổ',
        'badge': '🌱 Thế Hệ Vàng Trẻ',
        'badge_color': 'emerald',
        'target_type': 'rating',
        'default_impact': 10,
        'impact_range': (7, 13),
        'headlines': [
            "MĂNG MỌC THAY TRE: Lò đào tạo trẻ của {club} nở rộ với lứa tuyển thủ tài năng xuất chúng!",
            "TÀI KHÔNG ĐỢI TUỔI: Dàn tân binh {club} khiến giới chuyên môn ngỡ ngàng vì phản xạ siêu phàm!",
            "TƯƠNG LAI CỦA {region}: {club} gặt hái quả ngọt sau nhiều năm kiên trì đầu tư cho lứa trẻ!"
        ],
        'descriptions': [
            "Sau nhiều năm ươm mầm từ học viện, lứa tuyển thủ trẻ của {club} đã chính thức bước ra ánh sáng. Sức trẻ, kỹ năng cơ học siêu đẳng và sự khao khát khẳng định mình giúp thực lực của {club} tăng vọt.",
        ],
        'regional_bias': {'americas': 0.8, 'pacific': 2.2, 'emea': 1.0, 'china': 1.5},
    },
    'SC_EGO_CLASH': {
        'key': 'SC_EGO_CLASH',
        'title': 'Rạn Nứt Nội Bộ (Ego Clash)',
        'badge': '⚡ Rạn Nứt Nội Bộ',
        'badge_color': 'red',
        'target_type': 'form',
        'default_impact': -18,
        'impact_range': (-24, -12),
        'headlines': [
            "SÓNG NGẦM PHÒNG THAY ĐỒ: Các ngôi sao của {club} bất đồng chiến thuật sâu sắc!",
            "CÁI TÔI QUÁ LỚN: {club} rạn nứt nội bộ vì không ai chịu làm nền cho ai!",
            "BÁO ĐỘNG ĐỎ: Bầu không khí ngột ngạt đang hủy hoại sự gắn kết thi đấu của {club}!"
        ],
        'descriptions': [
            "Sở hữu nhiều cá tính mạnh mẽ trong cùng một màu áo, mâu thuẫn giữa các ngôi sao của {club} đã bùng nổ sau cánh gà. Sự nghi kỵ và thiếu ăn ý trong những pha phối hợp đang kéo tụt phong độ của đội bóng.",
        ],
        'regional_bias': {'americas': 1.5, 'pacific': 0.8, 'emea': 1.8, 'china': 1.0},
    },
    'SC_ONE_TRICK': {
        'key': 'SC_ONE_TRICK',
        'title': 'Quái Kiệt Dị Biệt Trỗi Dậy',
        'badge': '🎭 Quái Kiệt Trỗi Dậy',
        'badge_color': 'indigo',
        'target_type': 'form',
        'default_impact': 18,
        'impact_range': (14, 22),
        'headlines': [
            "LỐI ĐÁNH DỊ BIỆT: {club} khiến cả giải đấu điêu đứng bằng những bài vở không giống ai!",
            "BẬC THẦY SÁNG TẠO: {club} biến những đặc vụ ít người chơi thành vũ khí hủy diệt!",
            "CƠN ÁC MỘNG CHIẾN THUẬT: Đối thủ hoàn toàn bất lực trong việc giải mã bài đánh của {club}!"
        ],
        'descriptions': [
            "{club} đem đến sàn đấu những chiến thuật lập dị cùng dàn đặc vụ chẳng ai ngờ tới. Sự bất ngờ và tính toán quái chiêu khiến mọi đối thủ đều rơi vào thế bị động khi chạm trán họ.",
        ],
        'regional_bias': {'americas': 0.8, 'pacific': 1.5, 'emea': 1.0, 'china': 1.8},
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 2. LOGIC KIỂM TRA ĐIỀU KIỆN (ELIGIBILITY CHECKERS)
# ─────────────────────────────────────────────────────────────────────────────

def _get_club_history_context(campaign_id: int, old_year: int) -> Dict[str, Any]:
    """Lấy dữ liệu ngữ cảnh lịch sử của mùa giải trước (nếu có) để xét điều kiện."""
    context = {
        'champions_winner_id': None,
        'masters_winner_id': None,
        'major_winner_id': None,
        'runners_up_ids': set(),
        'top4_ids': set(),
        'bottom_ids': set(),
        'old_year': old_year,
    }

    season = CampaignSeason.query.filter_by(campaign_id=campaign_id, year=old_year).first()
    if season:
        context['champions_winner_id'] = season.champion_winner_id
        context['masters_winner_id'] = season.master_winner_id
        context['major_winner_id'] = season.major_winner_id

    placements = CampaignStagePlacement.query.filter_by(campaign_id=campaign_id, year=old_year).all()
    if placements:
        for p in placements:
            if p.rank == 2:
                context['runners_up_ids'].add(p.club_id)
            elif p.rank in (3, 4):
                context['top4_ids'].add(p.club_id)
            elif p.rank >= 18:
                context['bottom_ids'].add(p.club_id)

    return context


def check_scenario_eligibility(scenario_key: str, cs: CampaignClubState, history: Dict[str, Any]) -> bool:
    """Kiểm tra xem một CLB có đủ điều kiện hợp lý để nhận kịch bản này hay không."""
    cid = cs.club_id
    rating = cs.story_rating or 80

    if scenario_key == 'SC_CHAMP_CURSE':
        # Phải là đội vô địch Champions hoặc Masters mùa trước, hoặc nếu Year 1 thì là đội rating >= 92
        if history['champions_winner_id'] or history['masters_winner_id']:
            return cid in (history['champions_winner_id'], history['masters_winner_id'])
        return rating >= 92

    elif scenario_key == 'SC_SUPER_TEAM':
        # Đội top 2-6 hoặc có rating cao (87 - 94) nhưng chưa vô địch thế giới
        is_champ = cid in (history['champions_winner_id'], history['masters_winner_id'])
        if is_champ:
            return False
        return (rating >= 86) or (cid in history['runners_up_ids'] or cid in history['top4_ids'])

    elif scenario_key == 'SC_OIL_TYCOON':
        # Đội nhược tiểu nhóm dưới (rating <= 76) hoặc thuộc top bottom mùa trước
        return (rating <= 76) or (cid in history['bottom_ids'])

    elif scenario_key == 'SC_FIRE_SALE':
        # Đội tầm trung (rating 78 - 87) gặp khó khăn tài chính, không phải đương kim vô địch
        if cid == history['champions_winner_id']:
            return False
        return 77 <= rating <= 87

    elif scenario_key == 'SC_CINDERELLA':
        # Đội hạt giống thấp nhất (rating <= 75 hoặc bottom rank)
        return (rating <= 75) or (cid in history['bottom_ids'])

    elif scenario_key == 'SC_SILVER_CURSE':
        # Mùa trước về nhì (runner up) hoặc rating cao (88-93) nhưng luôn thiếu may mắn
        if cid in history['runners_up_ids']:
            return True
        return 88 <= rating <= 93

    elif scenario_key == 'SC_REVENGE_SQUAD':
        # Đội tầm trung/yếu (rating 72 - 79)
        return 71 <= rating <= 79

    elif scenario_key == 'SC_LAST_DANCE':
        # Đội kỳ cựu rating 82 - 91
        return 82 <= rating <= 91

    elif scenario_key == 'SC_RIOT_PATCH':
        # Các đội top mạnh (rating >= 84) dễ bị ảnh hưởng bởi meta
        return rating >= 84

    elif scenario_key == 'SC_VISA_HELL':
        # Bất kỳ đội nào có khả năng đi quốc tế (rating >= 78)
        return rating >= 78

    elif scenario_key == 'SC_TWITTER_BEEF':
        # Đội danh tiếng hoặc có rating >= 80
        return rating >= 80

    elif scenario_key == 'SC_GOLDEN_YOUTH':
        # Đội tầm trung đang xây dựng lại (rating 73 - 83)
        return 72 <= rating <= 83

    elif scenario_key == 'SC_EGO_CLASH':
        # Đội toàn sao (rating >= 87)
        return rating >= 87

    elif scenario_key == 'SC_ONE_TRICK':
        # Đội tầm trung (rating 73 - 85)
        return 73 <= rating <= 85

    return True


# ─────────────────────────────────────────────────────────────────────────────
# 3. DỰ THẢO KỊCH BẢN MÙA GIẢI (DRAFT GENERATOR)
# ─────────────────────────────────────────────────────────────────────────────

def generate_season_storylines_draft(campaign_id: int, target_year: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Máy tự động phân tích mùa cũ và dự thảo 3 đến 5 kịch bản tiêu điểm cho mùa giải mới.
    Đảm bảo tính cân bằng (1-2 vụ Rating Gốc, 2-3 vụ Phong Độ) và tôn trọng Thiên kiến Khu vực.
    """
    campaign = db.session.get(Campaign, campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    year = target_year if target_year else campaign.current_year
    old_year = year - 1

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign.id).all()
    if not club_states:
        return []

    history = _get_club_history_context(campaign.id, old_year)

    # Phân nhóm CLB theo khu vực và thông tin CLB
    clubs_by_id = {cs.club_id: cs for cs in club_states}
    all_clubs = Club.query.filter(Club.id.in_(list(clubs_by_id.keys()))).all()
    club_meta_map = {c.id: c for c in all_clubs}

    # Phân chia thành 2 nhóm kịch bản: Rating Gốc vs Phong Độ
    rating_scenarios = ['SC_SUPER_TEAM', 'SC_OIL_TYCOON', 'SC_FIRE_SALE', 'SC_GOLDEN_YOUTH']
    form_scenarios = [
        'SC_CHAMP_CURSE', 'SC_CINDERELLA', 'SC_SILVER_CURSE', 'SC_REVENGE_SQUAD',
        'SC_LAST_DANCE', 'SC_RIOT_PATCH', 'SC_VISA_HELL', 'SC_TWITTER_BEEF',
        'SC_EGO_CLASH', 'SC_ONE_TRICK'
    ]

    draft_storylines: List[Dict[str, Any]] = []
    used_club_ids = set()

    # Chọn 1 đến 2 kịch bản Rating Gốc
    num_rating_events = random.choice([1, 2])
    # Chọn 2 đến 3 kịch bản Phong Độ
    num_form_events = random.choice([2, 3])

    chosen_scenario_keys: List[str] = []

    # Ưu tiên nếu có Đương kim vô địch -> Lời nguyền vô địch
    if history['champions_winner_id'] or history['masters_winner_id']:
        chosen_scenario_keys.append('SC_CHAMP_CURSE')
        num_form_events -= 1

    # Bốc ngẫu nhiên kịch bản Rating Gốc
    random.shuffle(rating_scenarios)
    chosen_scenario_keys.extend(rating_scenarios[:num_rating_events])

    # Bốc ngẫu nhiên kịch bản Phong Độ
    remaining_form = [k for k in form_scenarios if k not in chosen_scenario_keys]
    random.shuffle(remaining_form)
    chosen_scenario_keys.extend(remaining_form[:num_form_events])

    # Gán từng kịch bản cho CLB phù hợp nhất dựa trên Regional Bias & Eligibility
    for skey in chosen_scenario_keys:
        sc_def = SCENARIO_CATALOG[skey]
        reg_bias = sc_def.get('regional_bias', {})

        # Tìm các ứng viên đủ điều kiện
        candidates = []
        for cs in club_states:
            cid = cs.club_id
            if cid in used_club_ids:
                continue

            club_obj = club_meta_map.get(cid)
            if not club_obj:
                continue

            region_slug = club_obj.region.slug if club_obj.region else 'americas'
            weight = reg_bias.get(region_slug, 1.0)

            if check_scenario_eligibility(skey, cs, history):
                candidates.append((cs, club_obj, weight))

        if not candidates:
            # Fallback nếu không có ai đạt chuẩn chặt chẽ
            for cs in club_states:
                cid = cs.club_id
                if cid not in used_club_ids:
                    c_obj = club_meta_map.get(cid)
                    if c_obj:
                        candidates.append((cs, c_obj, 1.0))

        if not candidates:
            continue

        # Chọn có trọng số
        cs_chosen, club_chosen, _ = random.choices(
            candidates,
            weights=[w for _, _, w in candidates],
            k=1
        )[0]

        used_club_ids.add(club_chosen.id)

        # Tính toán giá trị tác động ngẫu nhiên trong khoảng
        min_imp, max_imp = sc_def['impact_range']
        if min_imp < max_imp:
            impact_val = random.randint(min_imp, max_imp)
        else:
            impact_val = min_imp

        # Tạo headline & description động
        reg_name = club_chosen.region.name if club_chosen.region else 'Khu vực'
        headline_tmpl = random.choice(sc_def['headlines'])
        headline = headline_tmpl.format(club=club_chosen.name, region=reg_name)

        desc_tmpl = random.choice(sc_def['descriptions'])
        desc = desc_tmpl.format(club=club_chosen.name, region=reg_name)

        draft_storylines.append({
            'scenario_key': skey,
            'title': sc_def['title'],
            'badge': sc_def['badge'],
            'badge_color': sc_def['badge_color'],
            'target_type': sc_def['target_type'],
            'impact_value': impact_val,
            'club_id': club_chosen.id,
            'club_name': club_chosen.name,
            'club_short_code': club_chosen.short_code,
            'region_name': reg_name,
            'region_slug': club_chosen.region.slug if club_chosen.region else 'pacific',
            'current_story_rating': cs_chosen.story_rating,
            'current_form': cs_chosen.form_modifier,
            'headline': headline,
            'description': desc,
            'is_global': False,
        })

    return draft_storylines


# ─────────────────────────────────────────────────────────────────────────────
# 4. CHỐT KỊCH BẢN VÀ CẬP NHẬT DATABASE (COMMIT STORYLINES)
# ─────────────────────────────────────────────────────────────────────────────

def commit_season_storylines(campaign_id: int, storylines_data: List[Dict[str, Any]], year: Optional[int] = None) -> Dict[str, Any]:
    """
    Lưu các kịch bản đã được Người chơi (Đạo diễn) duyệt vào Database,
    đồng thời áp dụng cập nhật `story_rating` hoặc `form_modifier` cho các CLB.
    """
    campaign = db.session.get(Campaign, campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    target_year = year if year else campaign.current_year

    # Xóa các kịch bản cũ của năm này nếu có (để tránh trùng lặp)
    CampaignStoryline.query.filter_by(campaign_id=campaign.id, year=target_year).delete()

    created_records = []
    applied_updates = []

    for item in storylines_data:
        skey = item.get('scenario_key')
        sc_def = SCENARIO_CATALOG.get(skey, {})

        cid = item.get('club_id')
        target_type = item.get('target_type') or sc_def.get('target_type', 'form')
        impact_val = int(item.get('impact_value', sc_def.get('default_impact', 0)))

        title = item.get('title') or sc_def.get('title', 'Kịch bản Mùa giải')
        badge = item.get('badge') or sc_def.get('badge', '📰 Tiêu Điểm')
        badge_color = item.get('badge_color') or sc_def.get('badge_color', 'amber')
        headline = item.get('headline') or title
        desc = item.get('description', '')

        # Tạo bản ghi CampaignStoryline
        storyline_rec = CampaignStoryline(
            campaign_id=campaign.id,
            year=target_year,
            scenario_key=skey,
            title=title,
            headline=headline,
            description=desc,
            badge=badge,
            badge_color=badge_color,
            club_id=cid,
            target_type=target_type,
            impact_value=impact_val,
            is_global=bool(item.get('is_global', False)),
            metadata_json=json.dumps(item.get('metadata', {})),
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(storyline_rec)
        created_records.append(storyline_rec)

        # Cập nhật CampaignClubState nếu có club_id
        if cid:
            cs = CampaignClubState.query.filter_by(campaign_id=campaign.id, club_id=cid).first()
            if cs:
                old_rating = cs.story_rating
                old_form = cs.form_modifier

                if target_type == 'rating':
                    new_r = max(50, min(99, cs.story_rating + impact_val))
                    cs.story_rating = new_r
                    applied_updates.append({
                        'club_id': cid,
                        'field': 'story_rating',
                        'before': old_rating,
                        'after': new_r,
                        'delta': impact_val
                    })
                elif target_type == 'form':
                    new_f = max(-30, min(30, cs.form_modifier + impact_val))
                    cs.form_modifier = new_f
                    applied_updates.append({
                        'club_id': cid,
                        'field': 'form_modifier',
                        'before': old_form,
                        'after': new_f,
                        'delta': impact_val
                    })

    db.session.commit()

    return {
        'success': True,
        'year': target_year,
        'total_storylines': len(created_records),
        'applied_updates': applied_updates
    }


def get_active_campaign_storylines(campaign_id: int, year: Optional[int] = None) -> List[Dict[str, Any]]:
    """Lấy danh sách các kịch bản đang hoạt động của mùa giải hiện tại."""
    campaign = db.session.get(Campaign, campaign_id)
    if not campaign:
        return []

    target_year = year if year else campaign.current_year
    storylines = CampaignStoryline.query.filter_by(
        campaign_id=campaign.id, year=target_year
    ).order_by(CampaignStoryline.id.asc()).all()

    return [s.to_dict() for s in storylines]


def delete_campaign_storyline(storyline_id: int) -> bool:
    """Xóa một kịch bản cụ thể."""
    rec = db.session.get(CampaignStoryline, storyline_id)
    if not rec:
        return False
    db.session.delete(rec)
    db.session.commit()
    return True


def get_scenario_catalog() -> Dict[str, Any]:
    """Trả về toàn bộ danh mục 14 archetype kịch bản để phục vụ UI chọn lựa."""
    return SCENARIO_CATALOG
