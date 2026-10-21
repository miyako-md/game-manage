import {skinOf} from '../game-themes.js'
// Every QQ image is skinned: a game's own page takes its skin, and the cross-game
// pages (帮助, 我的账号, 活动, 近期活动, 日历, 我的总览) keep the obsidian (Wuwa) shell (D3).
export const sheetSkin=game=>skinOf(game)||'wuwa'
