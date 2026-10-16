/* These two persistent native events own room reset and perfect-dodge reward. */
(function () {
  "use strict";
  trigFuncs.trYwyStage = function (a) {
    var r = globalThis.__bbYWY;
    return !!r && !!r.stage && r.stage(a);
  };
  trigFuncs.trYwyDodge = function (a) {
    var r = globalThis.__bbYWY;
    return !!r && !!r.dodge && r.dodge(a);
  };
  trigFuncs.trYwyTalent = function (a, trigger, params) {
    var r = globalThis.__bbYWY;
    return !!r && !!r.talent && r.talent(a, params);
  };
})();
