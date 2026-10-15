import { accountCapabilities } from './accounts-api.js'
import { collectionState } from './snapshot-state.js'

export const CLOUD_GAMES = [
  {game_id:'wuthering_waves',display_name:'鸣潮',capabilities:['news','events']},
  {game_id:'nte',display_name:'异环',capabilities:['news','events']},
  {game_id:'endfield',display_name:'终末地',capabilities:['news','events']},
]
export const gameForAccount = account => ({kuro:'wuthering_waves',tajiduo:'nte',hypergryph:'endfield',skland:'endfield'})[account?.provider]
export const selectOverviewAccount = accounts => accounts.find(account=>account.provider==='skland') || accounts[0]

export function snapshotCollection(gameId, snapshots, includePublic=true) {
  return Object.entries(snapshots).filter(([cap])=>includePublic || !['news','events'].includes(cap)).map(([cap,snap])=>({
    game_id:gameId, capability:cap, state:collectionState(snap)==='failed' ? 'error' : snap?.state || 'never',
    last_success_at:snap?.fetched_at, error:snap?.error || snap?.poll_status?.error,
  }))
}

export function cloudGameView(account, snapshots={}, publicSnapshots={}) {
  const gameId=gameForAccount(account), caps=accountCapabilities(account), combined={...snapshots,...publicSnapshots}
  return {caps,snapshots:combined,
    game:{game_id:gameId,display_name:CLOUD_GAMES.find(game=>game.game_id===gameId)?.display_name,capabilities:[...caps,'news','events'],credentials_configured:account.state!=='revoked'},
    collection:snapshotCollection(gameId,combined),
  }
}

export function cloudOverviewView({ accounts=[], snapshotsByAccount={}, publicSnapshots={}, calendarSnapshots={} }={}) {
  const ownerGames=CLOUD_GAMES.filter(game=>accounts.some(account=>account.state!=='revoked' && gameForAccount(account)===game.game_id))
  const owners=Object.fromEntries(ownerGames.map(game=>[game.game_id,selectOverviewAccount(accounts.filter(account=>account.state!=='revoked' && gameForAccount(account)===game.game_id))]))
  const games=ownerGames.map(game=>{
    const owner=owners[game.game_id]
    return {...game,capabilities:owner.provider==='skland' ? ['account','stamina'] : accountCapabilities(owner),credentials_configured:true,
      platform:({skland:'终末地 / 森空岛档案',hypergryph:'终末地 / 鹰角寻访'})[owner.provider]}
  })
  const snapshots=Object.fromEntries(games.map(game=>{
    const owner=owners[game.game_id], raw=snapshotsByAccount[owner.account_id] || {}
    const privateSnapshots=owner.provider==='skland' && raw.account?.payload ? {
      ...raw,account:{...raw.account,payload:{schema_version:1,nickname:raw.account.payload.base?.name,level:raw.account.payload.base?.level}},
      stamina:{...raw.account,payload:raw.account.payload.stamina ? {schema_version:1,...raw.account.payload.stamina} : null},
    } : raw
    return [game.game_id,{...privateSnapshots,...publicSnapshots[game.game_id],...calendarSnapshots[game.game_id]}]
  }))
  const readErrors=Object.fromEntries(games.flatMap(game=>{
    const snapshot=Object.values(snapshots[game.game_id]).find(snap=>collectionState(snap)==='failed')
    const error=snapshot?.error || snapshot?.poll_status?.error || (snapshot ? '来源读取异常' : '')
    return error ? [[game.game_id,error]] : []
  }))
  return {ownerGames,owners,games,snapshots,readErrors,
    accounts:Object.fromEntries(games.map(game=>[game.game_id,{state:'connected'}])),
    collection:games.flatMap(game=>snapshotCollection(game.game_id,snapshots[game.game_id],false)),
  }
}
