/* Native battle exit lifecycle. Preserve the stock method and its result/arguments. */
(function () {
  "use strict";
  var proto = BattleJs.prototype;
  if (proto.__ywyExitWrapped) return;
  var original = proto.BattleExit;
  if (typeof original !== "function") throw new Error("YWY: bound BattleJs.BattleExit is absent");
  proto.BattleExit = function () {
    try {
      var r = globalThis.__bbYWY;
      if (r && typeof r.exitBattle === "function") r.exitBattle(this.Battle);
    } catch (e) { console.error("GamePlay", "[YWY] battle exit cleanup: " + e); }
    return original.apply(this, arguments);
  };
  proto.__ywyExitWrapped = true;
})();
