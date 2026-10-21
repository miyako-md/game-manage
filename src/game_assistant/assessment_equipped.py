"""Adapter-friendly equipped inputs. No inferred identity, area or item quality."""
import re
from .assessment import Configuration
from .wuwa_role_detail import role_detail_data

WUWA_NAMES={'攻击':'attack','攻击力':'attack','生命':'health','生命值':'health','防御':'defense','防御力':'defense','暴击':'crit_rate','暴击率':'crit_rate','暴击伤害':'crit_damage','共鸣效率':'energy_regen','普攻伤害加成':'basic_damage','重击伤害加成':'heavy_damage','共鸣技能伤害加成':'skill_damage','共鸣解放伤害加成':'liberation_damage','气动伤害加成':'aero_damage','冷凝伤害加成':'glacio_damage','热熔伤害加成':'fusion_damage','导电伤害加成':'electro_damage','衍射伤害加成':'spectro_damage','湮灭伤害加成':'havoc_damage','治疗效果加成':'healing_bonus'}


def _entries(value):
    # Sources leave unequipped slots as null and may send null for a whole list; neither is an item.
    return [(index,item) for index,item in enumerate(value if isinstance(value,list) else []) if isinstance(item,dict)]


def equipped_configuration(game,character,payload,observed_at=None):
    items=[]
    if game=='nte':
        role=next((r for r in payload.get('entries',[]) if str(r.get('id'))==character),None) if isinstance(payload,dict) else None
        if role:
            suit=role.get('suit') if isinstance(role.get('suit'),dict) else {}
            for group in ('core','pie'):
                for index,item in _entries(suit.get(group)):
                    source_id=str(item['id']) if item.get('id') is not None else None
                    items.append(dict(id=f'{group}:{index}:'+str(source_id or 'unknown'),source_id=source_id,source_group=group,
                        stats=[dict(canonical_id=p.get('id'),value=p.get('value'),unit=None) for _,p in _entries(item.get('properties'))]))
    elif (payload:=role_detail_data(payload,character)) is not None:
        phantoms=payload.get('phantom_data') if isinstance(payload.get('phantom_data'),dict) else {}
        for index,item in _entries(phantoms.get('equip_phantom_list')):
            stats=[]
            phantom=item.get('phantom_prop') if isinstance(item.get('phantom_prop'),dict) else {}
            # Kuro role detail lists every main/sub stat of an equipped echo (D2): complete when both
            # lists are real lists whose entries all parse. Only this snapshot path asserts completeness.
            complete=all(isinstance(item.get(group),list) and all(isinstance(p,dict) for p in item[group]) for group in ('main_props','sub_props')) and bool(item.get('main_props'))
            for group in ('main_props','sub_props'):
                props=item.get(group,[])
                for stat_index,p in _entries([props] if isinstance(props,dict) else props):
                    name=p.get('attribute_name') or p.get('name')
                    raw=p.get('attribute_value') if 'attribute_value' in p else p.get('value')
                    raw=str(raw).strip() if raw is not None else None
                    ratio=raw is not None and raw.endswith('%')
                    canonical=WUWA_NAMES.get(name)
                    if canonical in ('attack','health','defense'): canonical+='_'+('ratio' if ratio else 'flat')
                    unit='percent_points' if ratio else 'flat' if canonical in ('attack_flat','health_flat','defense_flat') else None
                    value=raw[:-1] if ratio else raw
                    if value is not None and not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value): value=None
                    complete=complete and None not in (canonical,value,unit)
                    stats.append(dict(canonical_id=canonical,value=value,unit=unit,role='main' if group=='main_props' else 'sub',observation_id=f'{group}:{stat_index}'))
            # Source resource ID alone does not identify a full-inventory item.
            source_id=str(phantom['phantom_id']) if phantom.get('phantom_id') is not None else None
            cost=next((c for c in (item.get('cost'),phantom.get('cost')) if type(c) is int),None)
            items.append(dict(id=f'echo:{index}:'+str(source_id or 'unknown'),source_id=source_id,kind='echo',stats=stats,
                              stats_complete=True if complete else None,cost=cost if cost is not None and 0<=cost<=99 else None))
    return Configuration.model_validate(dict(game=game,character_id=character,name='当前装备',source='equipped_snapshot',observed_at=observed_at,items=items))
