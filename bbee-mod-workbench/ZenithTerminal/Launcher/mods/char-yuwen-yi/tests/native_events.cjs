/* Offline contract scenarios. This does not emulate or certify Unity physics.
 * Run once with the complete frozen role batch: node mods/char-yuwen-yi/tests/native_events.cjs
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const actorSource = fs.readFileSync(path.join(__dirname, "../js/actor.js"), "utf8");
const inputPolicy = JSON.parse(fs.readFileSync(path.join(__dirname,"../gen/input-policy.json"),"utf8"));
let time = 0, shots = [], hudDisposed = 0;
class Vector2 { constructor(x,y) { this.x=x; this.y=y; } }
const battle = { get BattleTimeFp() { return time; }, BulletMgr: {
  CreateBulletByParams(a,id,pos,dir,scale,action,row) {
    assert.equal(id,20090101); assert.ok(row, "every projectile is booked to a real source skill row");
    const b={BaseID:id,UniqueId:1000+shots.length,RootCaster:a,Position:pos,
      ActionMgr:{CurrentActionName:action,ActionChangeAutoId:1},TargetMgr:{SetTarget(t){b.target=t;}}};
    shots.push({action,row,scale,pos,dir,b}); return b;
  }
}};
const U = {FloatToFp:x=>x,FpToFloat:x=>x,Vector2ToFp2:x=>x};
const C = {GamePlay:{BattleBase:{Cur:battle},Buff:{TagMaskByTagName:x=>x}},UnityEngine:{Vector2}};
const context = {console,Map,Set,pubfuncs:{},BB_YWY_INPUT_POLICY:inputPolicy,require:n=>n==="csharp"?C:n==="Core/Util"?{U}:assert.fail("unexpected import "+n)};
vm.createContext(context);vm.runInContext(actorSource,context,{filename:"actor.js"});
const F=context.pubfuncs,R=context.__bbYWY;
function player(uid=1) {
  const mp={2:0,3:0},owned=new Set(),buffs=new Map(),inputs=new Map();
  const p={BaseID:200901,UniqueId:uid,Faction:1,Dir:1,Position:{x:0,y:0},IsDead:false,CinemaControl:false,
    ActionMgr:{ActionChangeAutoId:0,CurrentActionName:"born",Time:0},
    Input:{GetCmdStatus(key){if(!inputs.has(key))inputs.set(key,{Pressing:false,LastPressTimeStamp:-1e9,LastStartPressingDir:{x:0,y:0},PressInputSatisfied:false});return inputs.get(key);},
      GetTimeEllaps:stamp=>time-stamp,
      SetPressInputSatisfied(key,satisfied){this.GetCmdStatus(key).PressInputSatisfied=satisfied;}},
    SkillMgr:{FindSkillByActionName:n=>({SkillActivate:{Action:n}})},
    ActionCountDown:{SetCountDown(n,t){this[n]=t;}},
    TriggerMgr:{FindTrigger:n=>owned.has(n)?{Idx:n}:null},
    Attr:{MaxHp:1000,MaxShield:0,Shield:0,GetMP:n=>mp[n],SetMP:(x,n)=>{mp[n]=x;},SetShield(x){this.Shield=x;}},
    BuffMgr:{AddBuff(n,d,s){buffs.set(n,{duration:d,strength:s});},Remove:n=>buffs.delete(n),
      RemoveByTagMask(n){this.removed=n;},RefreshBuffAttrForce(){p.Attr.MaxShield=1000*(buffs.get("ywy_shield")?.strength||0);}}};
  p.card=n=>owned.add((209000+n)*10+1);p.mp=mp;p.buffs=buffs;
  F.YwyBorn({Actor:p},{},null);return p;
}
function action(p,name,kind,input=0){p.ActionMgr.ActionChangeAutoId++;p.ActionMgr.CurrentActionName=name;p.ActionMgr.Time=0;return F.YwyStart({Actor:p},{kind,input},null);}
function press(p,key,y=0){const st=p.Input.GetCmdStatus(key);st.Pressing=true;st.LastPressTimeStamp=time;st.LastStartPressingDir={x:0,y};st.PressInputSatisfied=false;}
function release(p,key){p.Input.GetCmdStatus(key).Pressing=false;}
function can(p,move,input,group,extra={}){return F.YwyGate({Actor:p},{move,input,group,...extra},null);}
function hit(p,kind,target={UniqueId:20,Faction:2,Position:{x:2,y:0}}){
  if (!target.TagMgr)target.TagMgr={HasTag:n=>n==="Monster"};
  return F.YwyHit({Actor:p},{kind},{Attacker:p,Target:target});
}
function incoming(p,scale=1){const h={Target:p,IncomingDamageScale:scale,DestPassiveActionEnable:true};F.YwyGuard({Actor:p},{},h);return h;}
let scenarios=0;
function scenario(name,fn){fn();scenarios++;process.stdout.write("PASS "+name+"\n");}
scenario("birth owns full qi and Ultra, with no potential required",()=>{const p=player();assert.equal(p.mp[2],100);assert.equal(p.mp[3],100);assert.equal(R.view(p).shi,0);});
scenario("three enemies in one swing pay the same six qi once",()=>{const p=player(2);p.mp[2]=10;action(p,"ywy_sword1","sword1");for(let i=0;i<3;i++)hit(p,"sword1",{UniqueId:30+i,Faction:2});assert.equal(p.mp[2],16);});
scenario("next native action can earn its own reward",()=>{const p=player(3);p.mp[2]=10;action(p,"ywy_sword1","sword1");hit(p,"sword1");action(p,"ywy_sword2","sword2");hit(p,"sword2");assert.equal(p.mp[2],22);});
scenario("projectile hits cannot recursively earn basic attack qi",()=>{const p=player(4);p.mp[2]=10;const b={BaseID:20090101,RootCaster:p,UniqueId:400};F.YwyHit({Actor:b},{kind:"sword_echo"},{Attacker:b,Target:{Faction:2,UniqueId:22}});assert.equal(p.mp[2],10);});
scenario("ally and scenery of the same faction cannot build the loop",()=>{const p=player(5);p.mp[2]=10;action(p,"ywy_sword1","sword1");hit(p,"sword1",{Faction:1,UniqueId:23});assert.equal(p.mp[2],10);});
scenario("breakable opposing-faction pots do not pay enemy rewards",()=>{const p=player(55);p.mp[2]=10;action(p,"ywy_sword1","sword1");hit(p,"sword1",{Faction:2,UniqueId:24,TagMgr:{HasTag:()=>false}});assert.equal(p.mp[2],10);});
scenario("a valid precise guard suppresses damage and pays once",()=>{time=10;const p=player(6);p.mp[2]=10;p.mp[3]=0;action(p,"ywy_taiji_fist","fist");p.ActionMgr.Time=.1;time=10.1;for(let i=0;i<3;i++){const h=incoming(p);assert.equal(h.IncomingDamageScale,0);assert.equal(h.DestPassiveActionEnable,false);}assert.equal(p.mp[2],35);assert.equal(p.mp[3],12);assert.equal(R.view(p).guards,1);});
scenario("late failed guard has finite reduction and then expires",()=>{time=20;const p=player(7);action(p,"ywy_taiji_fist","fist");time=20.4;p.ActionMgr.Time=.4;assert.equal(incoming(p).IncomingDamageScale,.3);time=20.6;p.ActionMgr.Time=.6;assert.equal(incoming(p).IncomingDamageScale,1);});
scenario("changing action ends the guard immediately",()=>{time=30;const p=player(8);action(p,"ywy_taiji_fist","fist");time=30.1;action(p,"ywy_sword1","sword1");assert.equal(incoming(p).IncomingDamageScale,1);});
scenario("finisher and alternating styles cap taiji at five",()=>{const p=player(9);for(let i=0;i<10;i++){action(p,"ywy_sword3","sword3");hit(p,"sword3");action(p,"ywy_taiji_fist","fist");hit(p,"fist");time+=.2;}assert.equal(R.view(p).shi,5);});
scenario("base sword circle consumes taiji and has a fifteen percent shield cap",()=>{const p=player(10);R.states.get(p.UniqueId).shi=5;action(p,"ywy_circle_full","full");assert.equal(R.view(p).shi,0);assert.equal(p.Attr.Shield,150);});
scenario("Round Flow preserves excess taiji while keeping full-strength snapshot",()=>{const p=player(11);p.card(9);R.states.get(p.UniqueId).shi=5;action(p,"ywy_circle_full","full");assert.equal(R.view(p).shi,3);const h={Attacker:p,IncomingDamageScale:1};F.YwyDamage({Actor:p},{kind:"full"},h);assert.equal(h.IncomingDamageScale,1.5);});
scenario("three-way sword qi is a finite three-projectile event",()=>{const p=player(12);p.card(2);action(p,"ywy_zhenwu","zhenwu");let before=shots.length;for(let i=0;i<4;i++)F.YwyEmit({Actor:p},{kind:"zhenwu"},null);assert.equal(shots.length-before,3);});
scenario("boss attached sword is booked once per target per circle",()=>{const p=player(13);action(p,"ywy_circle_short","short");let before=shots.length;for(let i=0;i<3;i++)hit(p,"short");assert.equal(shots.length-before,1);assert.equal(shots.at(-1).action,"ywy_attached");});
scenario("escape excludes stand, cinema, death and cooldown",()=>{time=50;const p=player(14);p.ActionMgr.CurrentActionName="stand";assert.equal(F.YwyGate({Actor:p},{escape:true}),false);p.ActionMgr.CurrentActionName="behit_up";assert.equal(F.YwyGate({Actor:p},{escape:true}),true);action(p,"ywy_escape","escape");p.ActionMgr.CurrentActionName="behit_up";assert.equal(F.YwyGate({Actor:p},{escape:true}),false);time=57.01;assert.equal(F.YwyGate({Actor:p},{escape:true}),true);p.CinemaControl=true;assert.equal(F.YwyGate({Actor:p},{escape:true}),false);p.CinemaControl=false;p.IsDead=true;assert.equal(F.YwyGate({Actor:p},{escape:true}),false);});
scenario("ground dash has exactly two charges and a simulation-time recovery",()=>{time=60;const p=player(140);assert.equal(F.YwyGate({Actor:p},{dash:1}),true);action(p,"dash","dash");assert.equal(F.YwyGate({Actor:p},{dash:1}),false);assert.equal(F.YwyGate({Actor:p},{dash:2}),true);time=60.16;action(p,"dash2","dash");assert.equal(F.YwyGate({Actor:p},{dash:1}),false);assert.equal(F.YwyGate({Actor:p},{dash:2}),false);time=60.62;assert.equal(F.YwyGate({Actor:p},{dash:1}),true);});
scenario("first edge starts immediately and is consumed only on native start",()=>{time=100;const p=player(200);p.ActionMgr.CurrentActionName="stand";press(p,1);assert.equal(can(p,"ywy_sword1",1,1),true);assert.equal(can(p,"ywy_sword1",1,1),true);assert.equal(p.Input.GetCmdStatus(1).PressInputSatisfied,false);action(p,"ywy_sword1","sword1");assert.equal(p.Input.GetCmdStatus(1).PressInputSatisfied,true);p.ActionMgr.Time=.30;time=100.30;assert.equal(can(p,"ywy_sword2",1,1),false);assert.equal(p.Input.GetCmdStatus(1).Pressing,true);});
scenario("early second input stays buffered through the first strike and visible release",()=>{time=110;const p=player(201);press(p,1);action(p,"ywy_sword1","sword1");time=110.12;p.ActionMgr.Time=.12;press(p,1);release(p,1);assert.equal(can(p,"ywy_sword2",1,1),false);time=110+16/60;p.ActionMgr.Time=16/60;assert.equal(can(p,"ywy_sword1",1,1),false);assert.equal(can(p,"ywy_sword2",1,1),true);action(p,"ywy_sword2","sword2");p.ActionMgr.Time=.35;assert.equal(can(p,"ywy_sword3",1,1),false);});
scenario("second strike and finisher cannot be cut by native chain reset",()=>{
  time=120;const p=player(202);press(p,1);action(p,"ywy_sword2","sword2");
  time=120.10;p.ActionMgr.Time=.10;press(p,1);
  for(const age of [.16,17/60]){time=120+age;p.ActionMgr.Time=age;assert.equal(can(p,"ywy_sword3",1,1),false);}
  time=120+20/60;p.ActionMgr.Time=20/60;assert.equal(can(p,"ywy_sword3",1,1),true);action(p,"ywy_sword3","sword3");
  const thirdStart=time;time=thirdStart+.03;press(p,1);
  for(const age of [.080,.084,19/60,26/60]){time=thirdStart+age;p.ActionMgr.Time=age;assert.equal(can(p,"ywy_sword1",1,1),false);}
  time=thirdStart+27/60;p.ActionMgr.Time=27/60;assert.equal(can(p,"ywy_sword1",1,1),true);
});
scenario("old no-new-edge finisher and sword-qi failure sequences stay rejected",()=>{time=130;const p=player(203);press(p,1);action(p,"ywy_sword3","sword3");time=130.083;p.ActionMgr.Time=.083;assert.equal(can(p,"ywy_sword1",1,1),false);time=131;press(p,3);action(p,"ywy_zhenwu","zhenwu");time=131.164;p.ActionMgr.Time=.164;assert.equal(can(p,"ywy_zhenwu",3,2),false);time=131.30;p.ActionMgr.Time=.30;assert.equal(can(p,"ywy_zhenwu",3,2),false);press(p,3);assert.equal(can(p,"ywy_zhenwu",3,2),true);});
scenario("current action time wins over stale skill-chain elapsed time",()=>{time=140;const p=player(204);press(p,1);action(p,"ywy_sword1","sword1");time=140.02;press(p,1);p.SkillMgr.LastSkill={TimeEllaps:99};p.ActionMgr.CurrentActionName="ywy_sword3";p.ActionMgr.Time=.083;assert.equal(can(p,"ywy_sword1",1,1),false);});
scenario("consumed Attack stays held for charge, whose release is not a new attack",()=>{time=150;const p=player(205);press(p,1);action(p,"ywy_sword1","sword1");time=150.30;p.ActionMgr.Time=.30;assert.equal(p.Input.GetCmdStatus(1).Pressing,true);assert.ok(Math.abs(p.Input.GetTimeEllaps(p.Input.GetCmdStatus(1).LastPressTimeStamp)-.3)<1e-9);p.ActionMgr.CurrentActionName="ywy_charge";p.ActionMgr.Time=.2;assert.equal(can(p,"ywy_circle_short",0,8),false);release(p,1);assert.equal(can(p,"ywy_circle_short",0,8),true);assert.equal(can(p,"ywy_circle_full",0,8),false);p.ActionMgr.Time=.5;assert.equal(can(p,"ywy_circle_full",0,8),true);});
scenario("defensive dash can cancel before finisher recovery without replaying its input",()=>{time=160;const p=player(206);action(p,"ywy_sword3","sword3");p.ActionMgr.Time=.02;press(p,55);assert.equal(can(p,"dash",55,5,{dash:1}),true);action(p,"dash","dash");time=160.16;p.ActionMgr.Time=.16;assert.equal(can(p,"dash2",55,5,{dash:2}),false);press(p,55);assert.equal(can(p,"dash2",55,5,{dash:2}),true);});
scenario("neutral sword qi never replaces an unaffordable directional skill",()=>{time=170;const p=player(207);p.ActionMgr.CurrentActionName="stand";press(p,3,1);assert.equal(can(p,"ywy_zhenwu",3,2),false);time=170.01;press(p,3,0);assert.equal(can(p,"ywy_zhenwu",3,2),true);});
scenario("jump uses a fresh Jump edge and cannot restart its takeoff action",()=>{time=180;const p=player(208);p.ActionMgr.CurrentActionName="dropend";press(p,800);assert.equal(can(p,"jump",800,7),true);action(p,"jump","jump",800);time=180.2;p.ActionMgr.Time=.2;assert.equal(can(p,"jump2",800,7),false);press(p,800);assert.equal(can(p,"jump",800,7),false);assert.equal(can(p,"jump2",800,7),true);});
scenario("an expired preinput cannot trigger an action much later",()=>{time=190;const p=player(209);p.ActionMgr.CurrentActionName="stand";press(p,1);time=190.5;assert.equal(can(p,"ywy_sword1",1,1),false);});
scenario("a visual layer follows exactly one originating action instance",()=>{time=200;const p=player(210);action(p,"ywy_circle_full","full");const b=shots.at(-1).b;assert.equal(b.ActionMgr.CurrentActionName,"ywy_fx_circle");assert.equal(F.YwyVisualBind({Actor:b},{bound:"circle"}),true);assert.equal(b.target,p);action(p,"ywy_circle_full","full");assert.equal(F.YwyVisualAlive({Actor:b},{bound:"circle"}),false);F.YwyBulletDone({Actor:b},{},null);assert.equal(R.visuals.has(b.UniqueId),false);});
scenario("projectile impact visuals have a finite per-target event budget",()=>{time=210;const p=player(211);const b={BaseID:20090101,RootCaster:p,UniqueId:5000};const target={UniqueId:40,Faction:2,Position:{x:2,y:0},TagMgr:{HasTag:n=>n==="Boss"}};const before=shots.length;for(let i=0;i<3;i++)F.YwyHit({Actor:b},{kind:"zhenwu_bolt"},{Attacker:b,Target:target});assert.equal(shots.length-before,1);assert.equal(shots.at(-1).action,"ywy_fx_impact");F.YwyBulletDone({Actor:b},{},null);assert.equal(R.impacts.has(b.UniqueId),false);});
scenario("room transition clears taiji and temporary shield",()=>{const p=player(15);R.states.get(p.UniqueId).shi=5;p.buffs.set("ywy_shield",{});R.stage(p);assert.equal(R.view(p).shi,0);assert.equal(p.buffs.has("ywy_shield"),false);});
scenario("render view is read-only and cannot create a new actor state",()=>{const p={BaseID:200901,UniqueId:999,IsDead:false};let before=R.states.size;assert.equal(R.view(p),null);assert.equal(R.states.size,before);});
scenario("native battle exit releases state and HUD ownership",()=>{R.disposeHUD=()=>hudDisposed++;R.exitBattle(battle);assert.equal(R.states.size,0);assert.equal(hudDisposed,1);});
assert.deepEqual(Object.keys(R.errors),[]);
process.stdout.write(JSON.stringify({status:"passed",scenarios,scope:"offline event contract; Unity integration pending"})+"\n");
