"""Preference scoring: explicit user configuration or a built-in unofficial echo default; never damage/ranking."""
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction
from typing import Literal
from pydantic import Field, model_validator
from .assessment_contracts import Contract, Identifier, FiniteDecimal, WeightProfile
from .assessment_nte_math import InventoryError, ScoringSpec, ScoreInput, StatInput, score_item, number
import hashlib

Game = Literal['nte','wuthering_waves']
# Units define canonical semantics. Built-in WuWa defaults (assessment_defaults) use the echo formula below.
WUWA_STATS = {'attack_flat':'flat','attack_ratio':'ratio','health_flat':'flat','health_ratio':'ratio',
    'defense_flat':'flat','defense_ratio':'ratio','crit_rate':'ratio','crit_damage':'ratio',
    'energy_regen':'ratio','basic_damage':'ratio','heavy_damage':'ratio','skill_damage':'ratio',
    'liberation_damage':'ratio','aero_damage':'ratio','glacio_damage':'ratio','fusion_damage':'ratio',
    'electro_damage':'ratio','spectro_damage':'ratio','havoc_damage':'ratio','healing_bonus':'ratio'}
SKILL_DAMAGE=('basic_damage','heavy_damage','skill_damage','liberation_damage')
ELEMENT_DAMAGE=('glacio_damage','fusion_damage','electro_damage','aero_damage','spectro_damage','havoc_damage')
# Upstream WutheringWavesUID echo formula: weights are per percent point (flat values as shown in game).
ECHO_FORMULA='wuwa-echo-default-v1'
ECHO_COSTS=('1','3','4')
ECHO_GRADES=('c','b','a','s','ss','sss')
ECHO_GRADE_THRESHOLDS=tuple(Fraction(x) for x in ('0','0.48','0.6','0.7','0.78','0.84'))
# In-game maximum single values; with each profile's max selection they reproduce the upstream score_max.
ECHO_SUB_MAX={'attack_flat':'60','attack_ratio':'11.6','health_flat':'580','health_ratio':'11.6','defense_flat':'70','defense_ratio':'14.7',
    'crit_rate':'10.5','crit_damage':'21','energy_regen':'12.4',**{s:'11.6' for s in SKILL_DAMAGE}}
ECHO_MAIN_MAX={'1':{'attack_ratio':'18','health_ratio':'22.8','defense_ratio':'18'},
    '3':{'attack_ratio':'30','health_ratio':'30','defense_ratio':'38','energy_regen':'32',**{e:'30' for e in ELEMENT_DAMAGE}},
    '4':{'attack_ratio':'33','health_ratio':'33','defense_ratio':'41.8','crit_rate':'22','crit_damage':'44','healing_bonus':'26.4'}}
# The second main stat of an echo is fixed by its COST.
ECHO_MAIN_FIXED={'1':('health_flat','2280'),'3':('attack_flat','100'),'4':('attack_flat','150')}
ECHO_TEXT=('单件=Σ(词条显示值×权重，主词条按 COST 取权重)÷该 COST 理论满分×50（HALF_UP 两位）；'
    '总分=各件之和，满分 250；等级按占比 0/0.48/0.6/0.7/0.78/0.84 → c/b/a/s/ss/sss。')


class AssessmentStat(StatInput):
    role: Literal['main','sub'] | None = None


class EquippedInput(Contract):
    id: Identifier
    source_id: str | None = None
    source_group: str | None = None
    kind: Literal['drive','cartridge','echo'] | None = None
    stats: list[AssessmentStat] = Field(default_factory=list,max_length=100)
    stats_complete: bool | None = None
    cost: int | None = Field(default=None,ge=0,le=99)
    nte: ScoreInput | None = None


class Configuration(Contract):
    game: Game
    character_id: Identifier
    name: str = Field(min_length=1,max_length=80)
    source: Literal['user_configured','equipped_snapshot']
    observed_at: str | None = None
    items: list[EquippedInput] = Field(default_factory=list,max_length=32)

    @model_validator(mode='after')
    def game_inputs(self):
        if self.game=='wuthering_waves' and any(i.nte is not None or i.kind in ('drive','cartridge') for i in self.items): raise ValueError('game input mismatch')
        if self.game=='nte' and any(i.kind=='echo' or (i.nte and i.kind and i.nte.kind!=i.kind) for i in self.items): raise ValueError('game input mismatch')
        return self


class WuwaEchoProfile(Contract):
    main: dict[Literal['1','3','4'],dict[str,FiniteDecimal]]
    sub: dict[str,FiniteDecimal] = Field(max_length=100)
    # Stats forming the theoretical maximum (upstream max_main_props/max_sub_props); absent = the best possible.
    max_main: dict[Literal['1','3','4'],list[str]] | None = None
    max_sub: list[str] | None = Field(default=None,max_length=5)

    @model_validator(mode='after')
    def valid(self):
        if set(self.main)!=set(ECHO_COSTS): raise ValueError('main weights for COST 1, 3 and 4 required')
        allowed={c:set(ECHO_MAIN_MAX[c])|{ECHO_MAIN_FIXED[c][0]} for c in ECHO_COSTS}
        if any(not set(w)<=allowed[c] for c,w in self.main.items()) or not set(self.sub)<=set(ECHO_SUB_MAX): raise ValueError('echo stat not available there')
        if any(not 0<=v<=100 for w in (self.sub,*self.main.values()) for v in w.values()): raise ValueError('weight 0..100 required')
        if self.max_main is not None and (set(self.max_main)!=set(ECHO_COSTS) or any(len(v)!=len(set(v)) or not set(v)<=allowed[c] for c,v in self.max_main.items())): raise ValueError('invalid maximum selection')
        if self.max_sub is not None and (len(self.max_sub)!=len(set(self.max_sub)) or not set(self.max_sub)<=set(ECHO_SUB_MAX)): raise ValueError('invalid maximum selection')
        return self


def echo_max(profile:WuwaEchoProfile,cost:str)->Fraction:
    """Exact theoretical item maximum; the upstream score_max is this truncated (in floats) to 3 places."""
    weight=lambda weights,stat:Fraction(weights.get(stat,Decimal(0)))
    main=profile.main[cost]; fixed,fixed_value=ECHO_MAIN_FIXED[cost]
    value=lambda stat:Fraction(fixed_value if stat==fixed else ECHO_MAIN_MAX[cost][stat])
    if profile.max_main is not None: best_main=sum((weight(main,s)*value(s) for s in profile.max_main[cost]),Fraction())
    else: best_main=max(weight(main,s)*Fraction(v) for s,v in ECHO_MAIN_MAX[cost].items())+weight(main,fixed)*Fraction(fixed_value)
    subs={s:weight(profile.sub,s)*Fraction(v) for s,v in ECHO_SUB_MAX.items()}
    best_sub=sum((subs[s] for s in profile.max_sub),Fraction()) if profile.max_sub is not None else sum(sorted(subs.values(),reverse=True)[:5])
    return best_sub+best_main


def echo_grade(ratio:Fraction)->str:
    return ECHO_GRADES[max(i for i,t in enumerate(ECHO_GRADE_THRESHOLDS) if ratio>=t)]


class AssessmentModel(Contract):
    game: Game
    character_id: Identifier
    version: Identifier
    source: Literal['user_configured','builtin_default']
    # Built-in defaults only: where the weights come from.
    attribution: Literal['gpl_snapshot','self_made'] | None = None
    wuwa_weights: dict[str,FiniteDecimal] = Field(default_factory=dict,max_length=100)
    wuwa_echo_profile: WuwaEchoProfile | None = None
    nte_profile: WeightProfile | None = None
    nte_spec: ScoringSpec | None = None

    @model_validator(mode='after')
    def valid(self):
        if any(k not in WUWA_STATS or not 0<=v<=100 for k,v in self.wuwa_weights.items()):
            raise ValueError('explicit canonical stat and weight 0..100 required')
        if self.game=='nte' and (self.wuwa_weights or self.wuwa_echo_profile): raise ValueError('game formula mismatch')
        if self.wuwa_weights and self.wuwa_echo_profile: raise ValueError('one formula per model')
        if self.source=='builtin_default' and (self.game!='wuthering_waves' or self.wuwa_weights or not self.wuwa_echo_profile): raise ValueError('built-in defaults are WuWa echo profiles')
        if (self.attribution is not None)!=(self.source=='builtin_default'): raise ValueError('attribution belongs to a built-in default')
        if self.game=='wuthering_waves' and (self.nte_profile or self.nte_spec): raise ValueError('game formula mismatch')
        if self.nte_profile and self.nte_profile.character_id!=self.character_id: raise ValueError('character mismatch')
        if self.nte_profile and self.nte_profile.source!='user_configured': raise ValueError('explicit user configured provenance required')
        return self


def _rounded(value):
    # All preference values are nonnegative; exact HALF_UP mirrors NTE math.
    cents=(2*value.numerator*100+value.denominator)//(2*value.denominator)
    return f'{cents//100}.{cents%100:02d}'


def _text(value):
    with localcontext() as ctx:
        ctx.prec=50
        return format(Decimal(value.numerator)/Decimal(value.denominator),'f')


def _assess_core(configuration: Configuration, model: AssessmentModel, item_level=False):
    if (configuration.game,configuration.character_id)!=(model.game,model.character_id): raise ValueError('character/model mismatch')
    profile=model.wuwa_echo_profile if model.game=='wuthering_waves' else None
    base=dict(model_version=model.version,source=model.source,
        model_fingerprint=hashlib.sha256(model.model_dump_json().encode()).hexdigest(),
        weight_version=model.nte_profile.version if model.nte_profile else model.version,
        formula='nte-custom-weighting-v1' if model.game=='nte' else ECHO_FORMULA if profile else 'wuwa-custom-weighted-values-v1',
        formula_text='D=最高四项正副词条权重之和；驱动副项=10×面积×品质因子×权重/D；卡带副项=100×品质因子×权重/D；卡带主项=50×权重×当前/参考' if model.game=='nte' else ECHO_TEXT if profile else 'Σ(已知词条规范值×用户权重)；百分数除以100，平值不换算；每件加总。',
        status='unscorable',value=None,reason=None,contributions=[],
        # Built-in defaults are always marked unofficial; grades and maxima exist only for the echo formula.
        origin=model.source,unofficial=True if model.source=='builtin_default' else None,attribution=model.attribution,
        grade=None,max_value=(50 if item_level else 250) if profile else None)
    if item_level: base['cost']=configuration.items[0].cost if profile and configuration.items else None
    def unavailable(reason,status='unscorable'): return {**base,'reason':reason,'status':status}
    if model.game=='nte' and (model.nte_profile is None or model.nte_spec is None): return unavailable('NO_MODEL','unconfigured')
    if model.game=='wuthering_waves' and not model.wuwa_weights and not profile: return unavailable('NO_WEIGHTS','unconfigured')
    if not configuration.items: return unavailable('NO_EQUIPMENT')
    if len({item.id for item in configuration.items})!=len(configuration.items): return unavailable('DUPLICATE_ITEM')
    terms=[]; contributions=[]; ratio=None
    for item in configuration.items:
        if model.game=='nte':
            if item.nte is None: return unavailable('MISSING_EXPLICIT_NTE_INPUT')
            # A malformed number makes this item unscorable, as INVALID_VALUE does for Wuwa below.
            try: result=score_item(item.nte,model.nte_profile,model.nte_spec)
            except InventoryError as error: return unavailable(error.code)
            if result.status!='scored': return unavailable(result.reason,result.status)
            for contribution in result.contributions:
                exact=contribution.exact_fraction
                terms.append(Fraction(int(exact.numerator),int(exact.denominator)))
                contributions.append({'item_id':item.id,**contribution.model_dump(mode='json')})
        else:
            if item.stats_complete is not True: return unavailable('UNKNOWN_STAT_COMPLETENESS')
            cost=str(item.cost) if item.cost is not None else None
            # Unknown is not zero: an echo without a usable COST is not scorable.
            if profile and cost not in ECHO_COSTS: return unavailable('UNKNOWN_COST')
            seen=set()
            observations={};by_stat={};points=Fraction()
            for stat in item.stats:
                name=stat.canonical_id
                if name not in WUWA_STATS: return unavailable('UNKNOWN_STAT')
                seen.add(name)
                expected=WUWA_STATS[name]
                if stat.value is None: return unavailable('UNKNOWN_VALUE')
                if stat.unit not in ('flat','ratio','percent_points') or ('ratio' if stat.unit=='percent_points' else stat.unit)!=expected: return unavailable('UNIT_MISMATCH')
                if profile and stat.role is None: return unavailable('UNKNOWN_STAT_ROLE')
                try:
                    value=number(stat.value)
                except (ValueError,ArithmeticError): return unavailable('INVALID_VALUE')
                canonical=Fraction(value)/(100 if stat.unit=='percent_points' else 1)
                identity=(name,canonical,expected,stat.role)
                if stat.observation_id in observations:
                    if observations[stat.observation_id]!=identity:return unavailable('CONFLICTING_OBSERVATION')
                    continue
                if name in by_stat and (not stat.observation_id or any(not s.observation_id for s in by_stat[name])):return unavailable('AMBIGUOUS_DUPLICATE_STAT')
                if name in by_stat and (stat.role is None or any(s.role is None or stat.role==s.role for s in by_stat[name])):return unavailable('AMBIGUOUS_DUPLICATE_STAT')
                if stat.observation_id:observations[stat.observation_id]=identity
                by_stat.setdefault(name,[]).append(stat)
                if profile:
                    # Upstream weights are per displayed number: percent points, flat values as shown.
                    shown=canonical*100 if expected=='ratio' else canonical
                    weight=(profile.main[cost] if stat.role=='main' else profile.sub).get(name,Decimal(0)); term=shown*Fraction(weight)
                    points+=term
                    contributions.append(dict(item_id=item.id,contribution_id=name,value=_text(term),weight=str(weight),unit=expected,
                        current_value=_text(shown),exact_fraction=dict(numerator=str(term.numerator),denominator=str(term.denominator))))
                    continue
                weight=model.wuwa_weights.get(name,Decimal(0)); term=canonical*Fraction(weight)
                terms.append(term)
                contributions.append(dict(item_id=item.id,contribution_id=name,value=_text(term),weight=str(weight),unit=expected,
                    current_value=_text(canonical),exact_fraction=dict(numerator=str(term.numerator),denominator=str(term.denominator))))
            # Confirmed complete source lists prove absent canonical stats are zero.
            if not seen: return unavailable('NO_STAT_VALUES')
            if profile:
                maximum=echo_max(profile,cost)
                if maximum<=0: return unavailable('ZERO_MAXIMUM')
                ratio=points/maximum
                # The total adds the displayed item scores, as upstream does.
                terms.append(Fraction(_rounded(ratio*50)))
    total=sum(terms,Fraction())
    grade=None
    if profile: grade=echo_grade(ratio) if item_level else echo_grade(total/250)
    return {**base,'status':'scored','value':_rounded(total),'contributions':contributions,'grade':grade,
            'exact_fraction':dict(numerator=str(total.numerator),denominator=str(total.denominator)),
            'rounding_adjustment':_text(Fraction(_rounded(total))-total)}


def assess(configuration: Configuration,model: AssessmentModel):
    result=_assess_core(configuration,model)
    items=[];known=Fraction()
    for item in configuration.items:
        single=Configuration.model_validate({**configuration.model_dump(mode='python'),'items':[item]})
        score=_assess_core(single,model,item_level=True)
        items.append({'item_id':item.id,**score})
        if score['status']=='scored':known+=Fraction(int(score['exact_fraction']['numerator']),int(score['exact_fraction']['denominator']))
    # A duplicated item id rejects the whole set; adding up its items would count that item twice.
    has_known=result['reason']!='DUPLICATE_ITEM' and any(i['status']=='scored' for i in items)
    partial=(True if has_known else None) if result['status']=='unscorable' else False if result['status']=='scored' else None
    return {**result,'item_results':items,'partial':partial,'partial_known_total':_rounded(known) if partial else None}


def compare(a,b,model):
    left,right=assess(a,model),assess(b,model)
    result=dict(a=left,b=right,model_version=model.version,percent_delta=None,delta=None,reason=None)
    if left['status']!='scored' or right['status']!='scored': result['reason']='BOTH_CONFIGURATIONS_REQUIRE_SCORE'; return result
    def exact(score):
        value=score['exact_fraction'];return Fraction(int(value['numerator']),int(value['denominator']))
    baseline,other=exact(left),exact(right)
    with localcontext() as ctx:
        ctx.prec=128
        difference=other-baseline
        result['delta']=format((Decimal(difference.numerator)/Decimal(difference.denominator)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP),'f')
        result['exact_delta']=dict(numerator=str(difference.numerator),denominator=str(difference.denominator))
        if baseline==0: result['reason']='ZERO_BASELINE'
        else:
            percent=difference*100/baseline
            result['percent_delta']=format((Decimal(percent.numerator)/Decimal(percent.denominator)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP),'f')
    return result
