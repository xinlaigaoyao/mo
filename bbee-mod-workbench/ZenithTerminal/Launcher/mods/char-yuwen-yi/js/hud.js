/* Display only: no simulation state is created or changed by this callback. */
(function () {
  "use strict";
  var G = globalThis, ticks = G.BB_HUD_TICKS = G.BB_HUD_TICKS || {};
  var S = { ui: null, label: null, text: "", error: false };
  function remove() {
    if (S.label && !CSharpDefine_1.IsNull(S.label)) csharp_1.UnityEngine.Object.Destroy(S.label.gameObject);
    S.label = null; S.ui = null; S.text = "";
  }
  G.__bbYWY = G.__bbYWY || { states: new Map(), errors: {}, revision: 1 };
  G.__bbYWY.disposeHUD = remove;
  ticks["char-yuwen-yi/resource"] = function (ui) {
    try {
      var bj = BattleJs_1.default.Instance, b = bj && bj.Battle, a = b && b.PlayerSelf;
      var r = G.__bbYWY, v = a && a.BaseID === 200901 && r && r.view ? r.view(a) : null;
      if (!v) { remove(); return; }
      if (S.ui !== ui) {
        remove(); S.ui = ui;
        var CS = csharp_1, T = TransUtil_1.default, row = T.Query(ui.CsObj.transform, "TanlentIcons");
        var src = row && T.Query(row.transform, "TextCount", CS.TMPro.TextMeshProUGUI);
        if (!src) throw new Error("native talent label missing");
        var go = CS.UnityEngine.Object.Instantiate(src.gameObject, ui.CsObj.transform);
        go.name = "YwyResourceStatus";
        var rt = go.transform, V = CS.UnityEngine.Vector2;
        rt.anchorMin = new V(0, 1); rt.anchorMax = new V(0, 1); rt.pivot = new V(0, 1);
        rt.anchoredPosition = new V(32, -148); rt.sizeDelta = new V(680, 60);
        S.label = require("Core/Util").U.GetComponent(go, CS.TMPro.TextMeshProUGUI);
        S.label.alignment = CS.TMPro.TextAlignmentOptions.TopLeft;
        S.label.fontSize = 24; S.label.enableWordWrapping = false;
      }
      var dots = ""; for (var i = 0; i < 5; i++) dots += i < v.shi ? "●" : "○";
      var text = "真气 " + Math.round(v.qi) + "/100   太极 " + dots + "\n护盾 " + Math.round(v.shield) +
        "   脱身 " + (v.escape > 0 ? v.escape.toFixed(1) + "秒" : "就绪");
      if (text !== S.text) { S.label.TextAuto(text); S.text = text; }
      S.label.gameObject.SetActive(true);
    } catch (e) {
      if (!S.error) { S.error = true; console.error("GamePlay", "[YWY] resource HUD: " + e); }
    }
  };
})();
