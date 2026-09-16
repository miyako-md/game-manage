from game_assistant.adapters.neverness.parse import parse_gacha


def test_community_ratings_preserve_official_values_without_recalculating():
    raw = {'luckTitle': '一般过路人', 'luckType': 8, 'gachaDetails': [
        {'tab': '限定卡池', 'm': 90, 'details': [
            {'charid': '1036', 'rareCount': 80, 'luckyType': 4},
            {'charid': '1036', 'rareCount': 1, 'luckyType': 0},
        ]},
    ]}
    data = parse_gacha(raw)
    assert data.luck_title == '一般过路人'
    assert data.luck_type == 8
    assert [row.lucky_type for row in data.pools[0].details] == [4, 0]
    assert data.pools[0].guarantee == 90


def test_missing_and_new_ratings_do_not_become_a_known_rating():
    data = parse_gacha({'gachaDetails': [{'tab': '弧盘池', 'details': [
        {'charid': 'fork_test', 'luckyType': 99}, {'charid': 'fork_test'},
    ]}]})
    assert data.luck_title is None
    assert data.luck_type is None
    assert [row.lucky_type for row in data.pools[0].details] == [99, None]
