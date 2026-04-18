---
name: AI協作準則
description: "GitHub Copilot 和 Claude Code 的有效使用規範。包含 context 給法、prompt 撰寫、生成代碼驗收。使用時機：請 AI 生成超過 20 行代碼前、遇到 AI 反覆給錯答案時。"
---

# AI 協作準則 v1.0

---

## 一、給 Context 的標準格式

每次請 AI 生成代碼前，先提供以下資訊：

```
當前任務：[一句話說明要實作什麼]
所在檔案：[檔案路徑]
相關類型定義：[貼上相關的 interface / type]
已有的鄰近代碼：[貼上函式簽名或相關 store]
限制條件：[框架版本、不能改的部分、必須相容的 API]
```

---

## 二、Prompt 撰寫規則

**有效 Prompt 要素：**
- 說「做什麼」而不是「怎麼做」（讓 AI 選實作方式）
- 說清楚「不要做什麼」（比說「要做什麼」更有效）
- 給具體輸入輸出範例
- 指定錯誤處理方式

**範例對比：**

❌ 差：
```
幫我寫一個 chat 元件
```

✅ 好：
```
實作 ChatInput.vue 元件（Vue 3 Composition API + TypeScript）
- Props: disabled: boolean（預設 false）
- Emits: submit(message: string)
- 輸入框 + 送出按鈕，Enter 送出，Shift+Enter 換行
- disabled 時按鈕 grey out，不可輸入
- 不需要處理 loading 狀態（由父元件控制）
- 使用 Tailwind CSS，不用 scoped style
```

---

## 三、生成代碼驗收清單

AI 生成代碼後，必須逐項確認才能採用：

- [ ] 型別定義完整，沒有 `any`
- [ ] 沒有 hardcode 的 magic number 或字串
- [ ] 非同步操作有 `try/catch`
- [ ] 沒有引入你不熟悉的新套件（確認後才採用）
- [ ] 符合現有 code 風格（命名、結構）
- [ ] 實際在瀏覽器跑過，不是只看代碼

---

## 四、遇到 AI 反覆給錯答案時

```
Step 1：重新給 context，更明確說明「不要什麼」
Step 2：把錯誤的代碼貼回去，說「這樣不對，原因是 [X]，請修正」
Step 3：若連續三次仍錯 → 改為「只讓 AI 解釋邏輯，自己手寫」
Step 4：若問題是架構性的 → 先畫出架構圖再請 AI 填代碼
```

**禁止行為：**
- 不理解就直接貼入 AI 生成的代碼
- 因為 AI 說「應該沒問題」就跳過測試
- 讓 AI 一次生成超過 100 行且自己沒有逐行讀過
