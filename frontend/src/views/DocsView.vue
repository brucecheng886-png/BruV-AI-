<template>
  <div class="docs-root">
    <!-- KB Sidebar -->
    <aside class="kb-sidebar">
      <div class="kb-sidebar-header">
        <span class="kb-sidebar-title">知識庫</span>
        <el-button circle size="small" @click="openKbDialog(null)"><Plus :size="14" :stroke-width="1.5" /></el-button>
      </div>

      <ul class="kb-list">
        <li
          class="kb-item"
          :class="{ active: selectedKbId === null }"
          @click="selectKb(null)"
        >
          <FileStack :size="15" :stroke-width="1.5" class="kb-icon-lucide" />
          <span class="kb-name">全部文件</span>
          <span class="kb-count">{{ totalDocCount }}</span>
        </li>
        <li
          v-for="kb in kbs"
          :key="kb.id"
          class="kb-item-wrapper"
        >
          <div
            class="kb-item"
            :class="{ active: selectedKbId === kb.id, 'kb-item--drag-over': dragOverKbId === kb.id }"
            @click="selectKb(kb.id)"
            @dragover.prevent="dragOverKbId = kb.id"
            @dragleave.self="dragOverKbId = null"
            @drop.prevent="onDocDrop(kb.id)"
          >
            <button class="kb-expand-btn" @click.stop="toggleKbExpand(kb.id)">
              <component
                :is="expandedKbs.has(kb.id) ? ChevronDown : ChevronRight"
                :size="12" :stroke-width="2"
              />
            </button>
            <Database :size="14" :stroke-width="1.5" class="kb-icon-lucide" />
            <span class="kb-name">{{ kb.name }}</span>
            <span class="kb-count">{{ kb.doc_count }}</span>
            <el-dropdown @command="(cmd) => handleKbCommand(cmd, kb)" @click.stop trigger="click">
              <MoreHorizontal :size="14" :stroke-width="1.5" class="kb-more" />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">編輯</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>刪除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <!-- 展開的文件列表 -->
          <ul v-if="expandedKbs.has(kb.id)" class="kb-doc-list">
            <li v-if="kbDocsLoading.has(kb.id)" class="kb-doc-loading">載入中…</li>
            <li v-else-if="!kbDocs[kb.id] || kbDocs[kb.id].length === 0" class="kb-doc-empty">無文件</li>
            <li
              v-else
              v-for="doc in kbDocs[kb.id]"
              :key="doc.id"
              class="kb-doc-item"
              :class="{ active: selectedKbId === kb.id }"
              @click="selectDocFromKb(kb.id, doc)"
            >
              <FileText :size="11" :stroke-width="1.5" class="kb-doc-icon" />
              <span class="kb-doc-title">{{ (doc.title || doc.filename || '未命名').slice(0, 20) }}{{ (doc.title || doc.filename || '').length > 20 ? '…' : '' }}</span>
            </li>
          </ul>
        </li>
      </ul>

      <!-- Tag Filter -->
      <div v-if="tags.length > 0" class="tag-filter">
        <div class="tag-filter-title">
          <span>{{ tagManageMode ? '管理標籤' : '標籤篩選' }}</span>
          <div class="tag-filter-title-actions">
            <el-button
              link
              size="small"
              :type="tagManageMode ? 'primary' : ''"
              style="font-size:11px;padding:0 2px;"
              @click="toggleTagManage"
            >
              <Check v-if="tagManageMode" :size="12" :stroke-width="2" style="margin-right:2px;" />
              <Settings2 v-else :size="12" :stroke-width="1.5" style="margin-right:2px;" />
              {{ tagManageMode ? '完成' : '管理' }}</el-button>
          </div>
        </div>

        <!-- 批次操作列 -->
        <div v-if="tagManageMode" class="tag-batch-bar">
          <div class="tag-batch-row1">
            <el-checkbox
              :model-value="isAllTagsSelected"
              :indeterminate="isTagsIndeterminate"
              @change="toggleSelectAllTags"
            >{{ isAllTagsSelected ? '取消全選' : '全部選取' }}</el-checkbox>
            <span class="tag-batch-count">已選取 {{ selectedTagIds.size }} 個</span>
          </div>
          <div v-if="selectedTagIds.size > 0" class="tag-batch-row2">
            <el-button
              size="small"
              :loading="tagBatchWorking"
              @click="batchTagRemoveAll"
            >從所有文件移除</el-button>
            <el-button
              size="small"
              type="danger"
              :loading="tagBatchWorking"
              @click="batchTagDelete"
            >徹底刪除</el-button>
          </div>
        </div>

        <div :class="['tag-chips', { 'tag-chips--manage': tagManageMode }]">
          <el-tag
            v-for="tag in tags"
            :key="tag.id"
            size="small"
            :class="['tag-chip', { 'tag-chip--selected-manage': tagManageMode && selectedTagIds.has(tag.id) }]"
            :style="!tagManageMode && selectedTagId === tag.id
              ? { background: tag.color, borderColor: tag.color, color: '#fff', cursor: 'pointer' }
              : { borderColor: tag.color, color: tag.color, cursor: 'pointer' }"
            @click="tagManageMode ? toggleTagSelection(tag.id) : selectTag(tag.id)"
          >
            <el-checkbox
              v-if="tagManageMode"
              :model-value="selectedTagIds.has(tag.id)"
              size="small"
              style="margin-right:3px;vertical-align:middle;"
              @click.stop
              @change="toggleTagSelection(tag.id)"
            />
            {{ tag.name }}<span class="tag-chip-count"> {{ tag.doc_count }}</span>
            <el-dropdown
              v-if="!tagManageMode"
              trigger="click"
              @command="(cmd) => handleTagSidebarCommand(cmd, tag)"
              @click.stop
              style="margin-left:2px;"
            >
              <MoreHorizontal :size="12" :stroke-width="1.5" style="cursor:pointer;vertical-align:middle;" @click.stop />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="removeAll">從所有文件移除</el-dropdown-item>
                  <el-dropdown-item command="deleteTag" divided style="color:#f56c6c;">徹底刪除此標籤</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </el-tag>
        </div>
        <el-button link size="small" style="margin-top:6px;font-size:12px;" @click="showNewTagDialog = true">
          <Tag :size="12" :stroke-width="1.5" style="margin-right:3px;" /> 新增標籤
        </el-button>
      </div>
      <div v-else class="tag-filter">
        <div class="tag-filter-title">標籤篩選</div>
        <el-button link size="small" style="font-size:12px;" @click="showNewTagDialog = true">
          <Tag :size="12" :stroke-width="1.5" style="margin-right:3px;" /> 新增標籤
        </el-button>
      </div>

      <!-- 待審核區塊 -->
      <div v-if="pendingReviews.length > 0" class="pending-review-block">
        <div class="pending-review-title">
          待審核
          <span class="pending-review-badge">
            {{ pendingReviews.filter(r => r.suggested_kb_name).length > 0 ? `KB: ${pendingReviews.filter(r=>r.suggested_kb_name).length}` : '' }}
            {{ pendingReviews.filter(r => r.suggested_kb_name && r.suggested_tags?.length).length > 0 ? ' / ' : '' }}
            {{ pendingReviews.filter(r => r.suggested_tags?.length > 0).length > 0 ? `標籤: ${pendingReviews.filter(r=>r.suggested_tags?.length>0).length}` : '' }}
          </span>
        </div>
        <div class="pending-review-actions">
          <el-button size="small" type="primary" :loading="reviewConfirming" @click="confirmAllReviews">全部確認</el-button>
          <el-button size="small" :loading="reviewRejecting" @click="rejectAllReviews">全部拒絕</el-button>
        </div>
      </div>

      <div class="kb-sidebar-footer">
        <el-button size="small" plain style="width:100%;margin-bottom:6px;margin-left:0;" @click="openKbDialog(null)">
          <Plus :size="14" :stroke-width="1.5" style="margin-right:4px;" /> 新建知識庫
        </el-button>
        <el-button
          size="small"
          :type="trashMode ? 'danger' : ''"
          plain
          style="width:100%;margin-left:0;"
          @click="selectTrash"
        >
          <Trash2 :size="14" :stroke-width="1.5" style="margin-right:4px;" /> 垃圾桶
          <span v-if="trashTotal > 0" style="margin-left:4px;font-size:11px;">({{ trashTotal }})</span>
        </el-button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="docs-main" :style="{ marginRight: panelOpen ? (panelWidth + 16) + 'px' : '0' }">

      <!-- 麵包屑（主內容區頂部，獨立一列） -->
      <div class="main-breadcrumb">
        <span class="mbc-base">文件管理</span>
        <template v-if="trashMode">
          <span class="mbc-sep">/</span>
          <span class="mbc-current" style="color:#f56c6c;">🗑️ 垃圾桶</span>
        </template>
        <template v-else-if="selectedKb">
          <span class="mbc-sep">/</span>
          <span class="mbc-current">{{ selectedKb.icon }} {{ selectedKb.name }}</span>
        </template>
      </div>

      <!-- Toolbar -->
      <div class="docs-toolbar">

        <!-- 搜尋列（左側，佔滿剩餘空間） -->
        <div class="search-bar">
          <Search :size="15" :stroke-width="1.5" class="sbar-icon" />
          <input
            v-model="searchQuery"
            class="sbar-input"
            :placeholder="aiSearchEnabled ? 'AI 語意搜尋文件…' : '關鍵字搜尋標題…'"
            @keyup.enter="doSearch"
          />
          <button v-if="searchQuery" class="sbar-clear" @click="clearSearch" title="清除">
            <X :size="14" :stroke-width="2" />
          </button>
          <div class="sbar-divider" />
          <button class="sbar-send" :disabled="!searchQuery.trim() || searching" @click="doSearch" title="搜尋">
            <SendHorizontal v-if="!searching" :size="15" :stroke-width="1.5" />
            <Loader2 v-else :size="15" :stroke-width="1.5" class="lucide-spin" />
          </button>
          <div class="sbar-divider" />
          <button
            class="sbar-ai-toggle"
            :class="{ 'sbar-ai-toggle--on': aiSearchEnabled }"
            @click="aiSearchEnabled = !aiSearchEnabled"
            :title="aiSearchEnabled ? '切換為關鍵字搜尋' : '切換為 AI 搜尋'"
          >
            <Zap :size="13" :stroke-width="1.5" style="margin-right:3px;" />AI
          </button>
        </div>

        <!-- 上傳 / 匯入 / 全選（搜尋列右側，非垃圾桶模式） -->
        <template v-if="!trashMode">
          <el-upload
            :http-request="handleUpload"
            :show-file-list="false"
            accept=".pdf,.docx,.xlsx,.txt,.md,.html,.csv"
            :disabled="uploading"
          >
            <el-tooltip content="上傳文件" placement="bottom">
              <el-button type="primary" plain circle :loading="uploading">
                <Upload :size="14" :stroke-width="1.5" />
              </el-button>
            </el-tooltip>
          </el-upload>
          <input
            ref="importInputRef"
            type="file"
            accept=".xlsx"
            style="display:none"
            @change="handleImportExcel"
          />
          <el-tooltip content="匯入連結" placement="bottom">
            <el-button
              type="success"
              plain
              circle
              :loading="importing"
              @click="importInputRef.click()"
            ><Link :size="14" :stroke-width="1.5" /></el-button>
          </el-tooltip>

          <!-- 全選 checkbox（匯入右側，Gmail 風格） -->
          <div v-if="displayedDocs.length > 0 && !searchMode" class="gmail-select">
            <button
              class="gmail-select__box"
              :class="{ 'gmail-select__box--checked': isAllSelected, 'gmail-select__box--indeterminate': isIndeterminate }"
              @click="toggleSelectAll(!isAllSelected); isSelectMode = !isAllSelected"
              :title="isAllSelected ? '取消全選' : '全選'"
            >
              <span v-if="isAllSelected" class="gmail-select__tick" />
              <span v-else-if="isIndeterminate" class="gmail-select__dash" />
            </button>
            <el-dropdown trigger="click" placement="bottom-start" @command="handleSelectCommand">
              <button class="gmail-select__arrow">
                <ChevronDown :size="11" :stroke-width="2" />
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="all">全選</el-dropdown-item>
                  <el-dropdown-item command="none">全不選</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>

        <!-- 彈性空白 -->
        <div style="flex:1;"></div>

        <!-- 右側：批次操作 / 清空垃圾桶 / 垃圾桶全選 / 檢視切換 -->
        <div class="toolbar-right">

          <!-- 垃圾桶模式：全選 checkbox（Gmail 風格） -->
          <div v-if="trashMode && trashDocs.length > 0" class="gmail-select">
            <button
              class="gmail-select__box"
              :class="{ 'gmail-select__box--checked': isAllSelected, 'gmail-select__box--indeterminate': isIndeterminate }"
              @click="toggleSelectAll(!isAllSelected); isSelectMode = !isAllSelected"
              :title="isAllSelected ? '取消全選' : '全選'"
            >
              <span v-if="isAllSelected" class="gmail-select__tick" />
              <span v-else-if="isIndeterminate" class="gmail-select__dash" />
            </button>
            <el-dropdown trigger="click" placement="bottom-start" @command="handleSelectCommand">
              <button class="gmail-select__arrow">
                <ChevronDown :size="11" :stroke-width="2" />
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="all">全選</el-dropdown-item>
                  <el-dropdown-item command="none">全不選</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <!-- 批次操作列（選取後展開） -->
          <transition name="fade">
            <div v-if="selectedDocs.size > 0" class="batch-ops">
              <span class="batch-count">{{ selectedDocs.size }}</span>
              <template v-if="trashMode">
                <el-button
                  size="small"
                  :loading="batchRestoring"
                  @click="restoreSelected"
                ><RefreshCw :size="14" :stroke-width="1.5" /></el-button>
                <el-button
                  type="danger"
                  size="small"
                  :loading="batchPermanentDeleting"
                  @click="permanentDeleteSelected"
                ><Trash2 :size="14" :stroke-width="1.5" /></el-button>
              </template>
              <template v-else>
                <el-button
                  type="danger"
                  size="small"
                  :loading="batchDeleting"
                  @click="deleteSelected"
                ><Trash2 :size="14" :stroke-width="1.5" /></el-button>
              </template>
              <el-button size="small" @click="clearSelection"><X :size="14" :stroke-width="1.5" /></el-button>
            </div>
          </transition>

          <!-- 垃圾桶模式：清空垃圾桶 -->
          <el-button
            v-if="trashMode && selectedDocs.size === 0"
            type="danger"
            size="small"
            plain
            :loading="emptyingTrash"
            @click="emptyTrash"
          ><Trash2 :size="14" :stroke-width="1.5" /></el-button>

          <!-- 檢視切換 -->
          <el-button-group class="view-toggle">
            <el-button
              v-for="m in viewModes"
              :key="m.value"
              :type="viewMode === m.value ? 'primary' : ''"
              @click="switchView(m.value)"
              :title="m.label"
            >
              <component :is="m.icon" :size="14" :stroke-width="1.5" />
            </el-button>
          </el-button-group>

        </div>
      </div>

      <!-- Upload feedback -->
      <el-alert v-if="uploadError" type="error" :description="uploadError" show-icon closable
        @close="uploadError=''" style="margin:0 20px 12px;" />
      <el-alert v-if="uploadSuccess" type="success" description="文件上傳成功，後台處理中..." show-icon closable
        @close="uploadSuccess=false" style="margin:0 20px 12px;" />

      <!-- Search Results Mode -->
      <div v-if="searchMode" class="search-results-wrap">
        <div class="search-results-header">
          <span>AI 搜尋結果：「{{ lastQuery }}」</span>
          <span class="result-count">共 {{ searchResults.length }} 筆</span>
          <el-button link @click="clearSearch"><X :size="14" :stroke-width="1.5" style="margin-right:3px;" /> 清除搜尋</el-button>
        </div>
        <div v-if="searching" class="loading-center">
          <Loader2 :size="32" class="lucide-spin" />
          <p>語意搜尋中...</p>
        </div>
        <div v-else-if="searchResults.length === 0" class="empty-state">
          <el-empty description="沒有找到相關文件" />
        </div>
        <div v-else class="search-result-list">
          <div
            v-for="r in searchResults"
            :key="r.doc_id"
            class="search-result-card"
            @click="openPanelById(r.doc_id, r)"
          >
            <div class="src-thumb" :style="{ background: fileColor(r.file_type) }">
              <component :is="fileIcon(r.file_type)" :size="22" style="color:white" :stroke-width="1.5" />
            </div>
            <div class="src-body">
              <div class="src-title">{{ r.title }}</div>
              <div class="src-snippet">{{ r.snippet }}</div>
              <div class="src-meta">
                <el-tag v-if="r.knowledge_base_name" size="small" type="info">{{ r.knowledge_base_name }}</el-tag>
                <span class="score-badge">相似度 {{ (r.score * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Normal Content Area -->
      <div v-else class="docs-content">

        <!-- 垃圾桶視圖 -->
        <div v-if="trashMode" class="grid-view">
          <div v-if="trashLoading" class="loading-center">
            <Loader2 :size="32" class="lucide-spin" />
          </div>
          <el-empty v-else-if="trashDocs.length === 0" description="垃圾桶是空的" style="margin-top:80px;" />
          <div v-else class="grid-cards">
            <div
              v-for="doc in trashDocs"
              :key="doc.doc_id"
              class="doc-card doc-card--trash"
              :class="{ 'doc-card--selected': selectedDocs.has(doc.doc_id) }"
              @click="selectedDocs.has(doc.doc_id) ? toggleSelectDoc(doc.doc_id) : undefined"
            >
              <!-- 批次勾選 -->
              <div class="card-check-wrap card-check-wrap--visible" @click.stop="toggleSelectDoc(doc.doc_id)">
                <div class="card-check-btn" :class="{ 'card-check-btn--checked': selectedDocs.has(doc.doc_id) }">
                  <svg v-if="selectedDocs.has(doc.doc_id)" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M2 6l3 3 5-5" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </div>
              </div>
              <div class="card-thumb card-thumb--deleted" :style="{ background: fileColor(doc.file_type) }">
                <component :is="fileIcon(doc.file_type)" :size="36" style="color:rgba(255,255,255,0.4)" :stroke-width="1.5" />
                <span class="file-badge" style="opacity:0.5;">{{ (doc.file_type || 'FILE').toUpperCase() }}</span>
              </div>
              <div class="card-body">
                <div class="card-title" :title="doc.title" style="color:#94a3b8;">{{ doc.title }}</div>
                <div class="card-meta">
                  <span style="font-size:11px;color:#94a3b8;">已刪除</span>
                </div>
                <div class="card-kb" v-if="doc.knowledge_base_name">
                  <el-tag size="small" type="info" style="opacity:0.5;">{{ doc.knowledge_base_name }}</el-tag>
                </div>
                <div class="card-date" style="color:#94a3b8;">{{ doc.created_at?.slice(0, 10) }}</div>
              </div>
              <div class="card-actions" @click.stop>
                <el-button size="small" @click="restoreDoc(doc.doc_id)" title="還原">
                  <RefreshCw :size="13" :stroke-width="1.5" />
                </el-button>
                <el-button size="small" type="danger" @click="permanentDeleteDoc(doc.doc_id)" title="永久刪除">
                  <Trash2 :size="13" :stroke-width="1.5" />
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <!-- Grid View -->
        <div v-if="!trashMode && viewMode === 'grid'" class="grid-view">
          <div v-if="loading" class="loading-center">
            <Loader2 :size="32" class="lucide-spin" />
          </div>
          <el-empty v-else-if="docs.length === 0" description="此知識庫尚無文件，請上傳第一份文件" style="margin-top:80px;" />
          <div v-else class="grid-cards">
            <div
              v-for="doc in displayedDocs"
              :key="doc.doc_id"
              class="doc-card"
              :class="{ 'doc-card--selected': selectedDocs.has(doc.doc_id), 'doc-card--select-mode': isSelectMode }"
              :style="draggingDocId === doc.doc_id ? { opacity: 0.4, cursor: 'grabbing' } : {}"
              draggable="true"
              @dragstart="draggingDocId = doc.doc_id"
              @dragend="draggingDocId = null; dragOverKbId = null"
              @click="handleCardClick(doc)"
            >
              <!-- 批次勾選 checkbox -->
              <div
                class="card-check-wrap"
                :class="{ 'card-check-wrap--visible': selectedDocs.has(doc.doc_id) || isSelectMode }"
                @click.stop="handleCheckboxClick(doc.doc_id)"
              >
                <div class="card-check-btn" :class="{ 'card-check-btn--checked': selectedDocs.has(doc.doc_id) }">
                  <svg v-if="selectedDocs.has(doc.doc_id)" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M2 6l3 3 5-5" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </div>
              </div>
              <div class="card-thumb" :style="doc.cover_image_url ? {} : { background: fileColor(doc.file_type) }">
                <img v-if="doc.cover_image_url" :src="doc.cover_image_url" class="card-thumb-cover" />
                <template v-else>
                  <component :is="fileIcon(doc.file_type)" :size="36" style="color:white" :stroke-width="1.5" />
                  <span class="file-badge">{{ (doc.file_type || 'FILE').toUpperCase() }}</span>
                </template>
              </div>
              <div class="card-body">
                <div class="card-title" :title="doc.title">{{ doc.title }}</div>
                <div class="card-meta">
                  <span class="status-dot" :class="'dot-' + doc.status" />
                  <span class="status-text">{{ statusLabel(doc.status) }}</span>
                  <span class="chunk-count">{{ doc.chunk_count }} chunks</span>
                </div>
                <div class="card-kb" v-if="doc.kb_list && doc.kb_list.length > 0">
                  <el-tag
                    v-for="kb in doc.kb_list"
                    :key="kb.kb_id"
                    size="small"
                    type="info"
                    style="margin:1px 2px 1px 0;"
                  >{{ kb.kb_name }}</el-tag>
                </div>
                <div class="card-kb" v-else-if="doc.knowledge_base_name">
                  <el-tag size="small" type="info">{{ doc.knowledge_base_name }}</el-tag>
                </div>
                <div class="card-tags">
                  <el-tag
                    v-for="t in doc.tags"
                    :key="t"
                    size="small"
                    :closable="!isSelectMode"
                    :class="['card-tag-chip', { 'card-tag-chip--selected': isSelectMode && selectedChipTags.has(t) }]"
                    :style="getTagStyle(t)"
                    style="margin:1px 2px 1px 0;"
                    @click.stop="isSelectMode ? toggleChipTag(t) : undefined"
                    @close.stop="removeTagFromDocByName(t, doc)"
                  >{{ t }}</el-tag>
                  <el-popover trigger="click" placement="bottom-start" :width="200" :teleported="true">
                    <template #reference>
                      <el-button class="add-tag-btn" size="small" link @click.stop>＋ 標籤</el-button>
                    </template>
                    <div class="tag-picker">
                      <div
                        v-for="tag in tags"
                        :key="tag.id"
                        class="tag-pick-item"
                        @click="toggleTagOnDoc(tag, doc)"
                      >
                        <el-tag size="small" :style="getTagColorStyle(tag)">{{ tag.name }}</el-tag>
                        <Check v-if="doc.tags.includes(tag.name)" :size="14" :stroke-width="2" style="color:#67c23a" />
                      </div>
                      <div v-if="tags.length === 0" class="tag-pick-empty">尚無標籤</div>
                    </div>
                  </el-popover>
                </div>
                <div class="card-date">{{ doc.created_at?.slice(0, 10) }}</div>
              </div>
              <div class="card-actions" @click.stop>
                <el-dropdown @command="(cmd) => handleDocCommand(cmd, doc)">
                  <el-button link size="small"><MoreHorizontal :size="16" :stroke-width="1.5" /></el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="detail">查看詳情</el-dropdown-item>
                      <el-dropdown-item command="move">移至知識庫</el-dropdown-item>
                      <el-dropdown-item
                        command="delete"
                        divided
                        :style="{ color: '#f56c6c' }"
                      >{{ ['pending','processing'].includes(doc.status) ? '取消上傳' : '刪除' }}</el-dropdown-item>
                      <el-dropdown-item
                        command="permanent-delete"
                        :style="{ color: '#f56c6c', fontWeight: '600' }"
                      >徹底刪除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </div>
        </div>

        <!-- Table View -->
        <div v-else-if="!trashMode && viewMode === 'table'" class="table-view">
          <el-table
            :data="displayedDocs"
            v-loading="loading"
            style="width:100%"
            stripe
            highlight-current-row
            @row-click="openPanel"
          >
            <el-table-column label="標題" prop="title" min-width="200" show-overflow-tooltip />
            <el-table-column label="知識庫" width="130">
              <template #default="{ row }">
                <el-tag v-if="row.knowledge_base_name" size="small" type="info">
                  {{ row.knowledge_base_name }}
                </el-tag>
                <span v-else style="color:#bbb;font-size:12px;">未分類</span>
              </template>
            </el-table-column>
            <el-table-column label="標籤" width="120">
              <template #default="{ row }">
                <template v-if="row.tags && row.tags.length">
                  <el-tag
                    v-for="t in row.tags.slice(0, 2)"
                    :key="t"
                    size="small"
                    :style="getTagStyle(t)"
                    style="margin:1px;"
                  >{{ t }}</el-tag>
                  <span v-if="row.tags.length > 2" style="font-size:11px;color:#94a3b8;"> +{{ row.tags.length - 2 }}</span>
                </template>
                <span v-else style="color:#bbb;font-size:12px;">—</span>
              </template>
            </el-table-column>
            <el-table-column label="類型" prop="file_type" width="70" align="center">
              <template #default="{ row }">
                <span style="font-size:12px;font-weight:600;color:#64748b">
                  {{ (row.file_type || '—').toUpperCase() }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="狀態" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Chunks" prop="chunk_count" width="80" align="center" />
            <el-table-column label="建立時間" width="140">
              <template #default="{ row }">{{ row.created_at?.slice(0, 16).replace('T', ' ') }}</template>
            </el-table-column>
            <el-table-column label="操作" width="130" align="center">
              <template #default="{ row }">
                <el-button size="small" link @click.stop="openPanel(row)"><Eye :size="14" :stroke-width="1.5" /> 詳情</el-button>
                <el-popconfirm title="確定刪除此文件？" @confirm="deleteDoc(row.doc_id)">
                  <template #reference>
                    <el-button size="small" link type="danger" @click.stop><Trash2 :size="14" :stroke-width="1.5" /></el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- Node View -->
        <div v-else-if="!trashMode && viewMode === 'node'" class="node-view">
          <div v-if="cyLoading" class="loading-center">
            <Loader2 :size="32" class="lucide-spin" />
            <p>建立節點圖...</p>
          </div>
          <div ref="cyContainer" class="cy-container" />
          <div class="cy-legend">
            <div v-for="kb in kbs" :key="kb.id" class="legend-item">
              <span class="legend-dot" :style="{ background: kb.color }" />
              <span>{{ kb.icon }} {{ kb.name }}</span>
            </div>
            <div class="legend-item">
              <span class="legend-dot" style="background:#94a3b8" />
              <span>未分類</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="!searchMode && !trashMode && viewMode !== 'node'" class="pagination-bar">
        <span class="pagination-info">共 {{ total }} 篇</span>
        <div class="pagination-right">
          <el-select v-model="pageSize" size="small" style="width:96px" @change="handlePageSizeChange">
            <el-option :value="25" label="25 篇/頁" />
            <el-option :value="50" label="50 篇/頁" />
            <el-option :value="100" label="100 篇/頁" />
          </el-select>
          <el-pagination
            v-model:current-page="page"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next"
            @current-change="loadDocs"
          />
        </div>
      </div>
    </main>

    <!-- Right Detail Panel -->
    <aside v-if="panelDoc" ref="panelRef" class="detail-panel"
      :class="{ 'panel-visible': panelOpen }"
      :style="{ width: panelWidth + 'px' }">
      <div class="panel-resize-handle" @mousedown.prevent="onPanelResizeStart"></div>
        <div class="panel-header">
          <div class="panel-thumb" :style="{ background: fileColor(panelDoc.file_type) }">
            <component :is="fileIcon(panelDoc.file_type)" :size="18" style="color:white" :stroke-width="1.5" />
          </div>
          <div class="panel-title-wrap">
            <div class="panel-title" :title="panelDoc.title">{{ panelDoc.title }}</div>
            <el-tag :type="statusTagType(panelDoc.status)" size="small">{{ statusLabel(panelDoc.status) }}</el-tag>
          </div>
          <el-button link @click="closePanel"><X :size="16" :stroke-width="1.5" /></el-button>
        </div>

        <el-tabs v-model="panelTab" class="panel-tabs">

          <!-- ══════════════════════════════════════════
               Tab 1：概覽（資訊 + 編輯 + 完整內容）
          ══════════════════════════════════════════ -->
          <el-tab-pane label="概覽" name="info">
            <el-scrollbar class="overview-scroll">
              <div class="overview-body">

                <!-- 區塊 1：基本資訊 + 可編輯標題 -->
                <div class="section-block">
                  <div class="section-title">基本資訊</div>

                  <!-- 標題（可直接編輯） -->
                  <div class="ov-field">
                    <div class="ov-label">標題</div>
                    <el-input v-model="editForm.title" placeholder="文件標題" maxlength="200" size="small" />
                  </div>

                  <!-- 來源連結 -->
                  <div class="ov-field">
                    <div class="ov-label">來源連結</div>
                    <div v-if="panelDoc.source_url" class="ov-url-row">
                      <el-link :href="panelDoc.source_url" target="_blank" type="primary" class="ov-url-link">
                        {{ panelDoc.source_url }}
                      </el-link>
                      <el-button link size="small" @click="copySourceUrl(panelDoc.source_url)"
                        style="flex-shrink:0;padding:0 4px;">
                        <Copy :size="13" :stroke-width="1.5" />
                      </el-button>
                    </div>
                    <span v-else class="ov-val-muted">—</span>
                  </div>

                  <!-- 知識庫 -->
                  <div class="ov-field">
                    <div class="ov-label">知識庫</div>
                    <div class="ov-kb-row">
                      <span>{{ panelDoc.knowledge_base_name || '未分類' }}</span>
                      <el-button link size="small" @click="openMoveDialog(panelDoc)">
                        <FolderInput :size="13" :stroke-width="1.5" style="margin-right:3px;" /> 移動
                      </el-button>
                    </div>
                  </div>

                  <!-- 純顯示欄位 -->
                  <div class="ov-field ov-row-3">
                    <div class="ov-stat">
                      <div class="ov-stat-label">檔案類型</div>
                      <div class="ov-stat-val">{{ (panelDoc.file_type || '—').toUpperCase() }}</div>
                    </div>
                    <div class="ov-stat">
                      <div class="ov-stat-label">Chunks</div>
                      <div class="ov-stat-val">{{ panelDoc.chunk_count ?? '—' }}</div>
                    </div>
                    <div class="ov-stat">
                      <div class="ov-stat-label">建立時間</div>
                      <div class="ov-stat-val ov-stat-date">{{ panelDoc.created_at?.slice(0, 10) }}</div>
                    </div>
                  </div>

                  <div v-if="panelDoc.error_message" class="ov-field">
                    <div class="ov-label" style="color:#ef4444">錯誤訊息</div>
                    <div class="ov-val-error">{{ panelDoc.error_message }}</div>
                  </div>
                </div>

                <!-- 區塊 2：描述與註記（可編輯） -->
                <div class="section-block">
                  <div class="section-title">描述與註記</div>
                  <div class="ov-field">
                    <div class="ov-label">描述</div>
                    <el-input v-model="editForm.description" type="textarea" :rows="3"
                      placeholder="簡短說明此文件的用途或來源…" maxlength="500" show-word-limit size="small" />
                  </div>
                  <div class="ov-field" style="margin-top:10px;">
                    <div class="ov-label">註記</div>
                    <el-input v-model="editForm.notes" type="textarea" :rows="4"
                      placeholder="個人備註、待辦事項、重要提醒…" maxlength="1000" show-word-limit size="small" />
                  </div>
                </div>

                <!-- 區塊 3：完整內容（可展開） -->
                <div class="section-block">
                  <div class="section-title section-title--toggle" @click="toggleContentExpand">
                    <span>完整內容</span>
                    <ChevronDown :size="15" :stroke-width="1.5"
                      :style="{ transform: contentExpanded ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform .2s' }" />
                  </div>
                  <div v-show="contentExpanded" class="ov-content-body">
                    <div v-if="contentLoading" class="loading-center" style="height:80px;">
                      <Loader2 :size="24" class="lucide-spin" />
                    </div>
                    <template v-else-if="contentLoaded">
                      <div v-if="panelDoc.file_type === 'xlsx' || panelDoc.file_type === 'csv'" class="content-xlsx-hint">
                        💡 Excel / CSV 建議於「Chunks」tab 查看
                      </div>
                      <pre class="full-content">{{ fullContent || '（此文件尚無可讀內容）' }}</pre>
                    </template>
                    <div v-else class="loading-center" style="height:60px;color:#94a3b8;font-size:13px;">
                      載入中…
                    </div>
                  </div>
                </div>

                <!-- 試算表區塊（僅 xlsx/csv） -->
                <div v-if="panelDoc.file_type === 'xlsx' || panelDoc.file_type === 'csv'" class="section-block">
                  <div class="section-title section-title--toggle" @click="toggleSheetExpand">
                    <span>試算表預覽</span>
                    <ChevronDown :size="15" :stroke-width="1.5"
                      :style="{ transform: sheetExpanded ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform .2s' }" />
                  </div>
                  <div v-show="sheetExpanded" class="ov-sheet-body">
                    <div v-if="sheetLoading" class="loading-center" style="height:80px;">
                      <Loader2 :size="24" class="lucide-spin" />
                    </div>
                    <div v-else-if="sheetError" class="loading-center" style="color:#ef4444;height:60px;">{{ sheetError }}</div>
                    <template v-else-if="sheetNames.length > 0">
                      <div v-if="sheetNames.length > 1" class="sheet-tab-bar">
                        <el-tabs v-model="activeSheet" type="card" size="small">
                          <el-tab-pane v-for="name in sheetNames" :key="name" :label="name" :name="name" />
                        </el-tabs>
                      </div>
                      <div class="sheet-scroll">
                        <div class="sheet-table-wrap">
                          <table class="sheet-table" v-html="sheetHtml[activeSheet] || ''" />
                        </div>
                      </div>
                    </template>
                    <div v-else class="loading-center" style="height:60px;color:#94a3b8;font-size:13px;">
                      載入中…
                    </div>
                  </div>
                </div>

                <!-- 區塊 4：操作按鈕 -->
                <div class="section-block ov-actions-block">
                  <el-button type="warning" plain size="small" :loading="reanalyzing" @click="reanalyzeDoc">
                    <RefreshCw :size="14" :stroke-width="1.5" style="margin-right:5px;" /> 重新 AI 分析
                  </el-button>
                  <el-button type="primary" size="small" :loading="editSaving" @click="saveDocMeta">
                    儲存
                  </el-button>
                  <el-button type="danger" plain size="small" @click="deleteDoc(panelDoc.doc_id)">
                    <Trash2 :size="14" :stroke-width="1.5" style="margin-right:5px;" /> 刪除文件
                  </el-button>
                </div>

              </div>
            </el-scrollbar>
          </el-tab-pane>

          <!-- ══════════════════════════════════════════
               Tab 2：Chunks（維持原有邏輯）
          ══════════════════════════════════════════ -->
          <el-tab-pane name="chunks">
            <template #label>
              Chunks
              <el-badge v-if="chunksTotal > 0" :value="chunksTotal" :max="999" class="chunk-badge" />
            </template>
            <div v-if="chunksLoading" class="loading-center">
              <Loader2 :size="28" class="lucide-spin" />
            </div>
            <template v-else>
              <div class="chunks-toolbar">
                <el-tag type="info" size="small">共 {{ chunksTotal }} 個</el-tag>
                <el-pagination
                  v-if="chunksTotal > CHUNK_PAGE_SIZE"
                  v-model:current-page="chunkPage"
                  :page-size="CHUNK_PAGE_SIZE"
                  :total="chunksTotal"
                  layout="prev, pager, next"
                  small
                  @current-change="loadChunks"
                />
              </div>
              <el-empty v-if="chunks.length === 0" description="尚無 Chunks" />
              <el-scrollbar class="chunks-scroll">
                <div v-for="chunk in chunks" :key="chunk.id" class="chunk-card">
                  <div class="chunk-header">
                    <el-tag size="small" type="primary">#{{ chunk.index }}</el-tag>
                    <el-tag v-if="chunk.page_number != null" size="small" type="info">
                      第 {{ chunk.page_number }} 頁
                    </el-tag>
                    <span class="chunk-len">{{ chunk.content.length }} 字元</span>
                  </div>
                  <p class="chunk-content">{{ chunk.content }}</p>
                </div>
              </el-scrollbar>
            </template>
          </el-tab-pane>

        </el-tabs>
      </aside>

    <!-- KB Dialog -->
    <el-dialog v-model="showKbDialog" :title="editKb ? '編輯知識庫' : '新建知識庫'" width="420px" destroy-on-close>
      <el-form :model="kbForm" label-width="70px">
        <el-form-item label="名稱">
          <el-input v-model="kbForm.name" placeholder="知識庫名稱" maxlength="50" />
        </el-form-item>
        <el-form-item label="圖示">
          <el-input v-model="kbForm.icon" placeholder="📚" maxlength="4" style="width:80px;margin-right:8px;" />
          <span style="font-size:24px;">{{ kbForm.icon }}</span>
        </el-form-item>
        <el-form-item label="色彩">
          <div class="color-swatches">
            <div
              v-for="c in COLOR_PRESETS"
              :key="c"
              class="swatch"
              :style="{ background: c, outline: kbForm.color === c ? '3px solid #1e293b' : '' }"
              @click="kbForm.color = c"
            />
          </div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="kbForm.description" type="textarea" :rows="2" placeholder="選填說明" />
        </el-form-item>
        <!-- 進階設定（可收合） -->
        <div class="kb-advanced-toggle" @click="showKbAdvanced = !showKbAdvanced">
          <span class="kb-advanced-line"></span>
          <span class="kb-advanced-label">進階設定（選填）{{ showKbAdvanced ? ' ▴' : ' ▾' }}</span>
          <span class="kb-advanced-line"></span>
        </div>
        <div v-show="showKbAdvanced">
          <el-form-item label="Embedding">
            <el-select
              v-model="kbForm.embedding_model"
              placeholder="使用全域設定"
              clearable
              style="width:100%;"
              @change="onEmbeddingChange"
            >
              <el-option
                v-for="m in embeddingModels"
                :key="m.id || m.name"
                :label="m.name + (m.provider ? ' (' + m.provider + ')' : '')"
                :value="m.name"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="Chunk 大小">
            <el-input-number v-model="kbForm.chunk_size" :min="100" :max="4000" :step="50" controls-position="right" style="width:160px;" />
            <span style="margin-left:8px;font-size:12px;color:#94a3b8;">留空使用全域設定</span>
          </el-form-item>
          <el-form-item label="語言">
            <el-select v-model="kbForm.language" style="width:160px;">
              <el-option label="自動偵測" value="auto" />
              <el-option label="繁體中文" value="zh-Hant" />
              <el-option label="英文" value="en" />
              <el-option label="日文" value="ja" />
            </el-select>
          </el-form-item>
          <el-form-item label="Re-ranker">
            <el-switch
              :model-value="kbForm.rerank_enabled === true"
              @update:model-value="v => kbForm.rerank_enabled = v ? true : (kbForm.rerank_enabled === false ? null : false)"
            />
            <el-button size="small" link style="margin-left:8px;" @click="kbForm.rerank_enabled = null">使用全域</el-button>
            <span style="margin-left:8px;font-size:12px;color:#94a3b8;">{{ kbForm.rerank_enabled === null ? '使用全域設定' : (kbForm.rerank_enabled ? '啟用' : '關閉') }}</span>
          </el-form-item>
          <el-form-item label="Top-K">
            <el-input-number v-model="kbForm.default_top_k" :min="1" :max="50" controls-position="right" style="width:160px;" />
            <span style="margin-left:8px;font-size:12px;color:#94a3b8;">留空使用全域設定</span>
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showKbDialog = false">取消</el-button>
        <el-button type="primary" @click="saveKb" :loading="kbSaving">儲存</el-button>
      </template>
    </el-dialog>

    <!-- Move to KB Dialog -->
    <el-dialog v-model="showMoveDialog" title="移至知識庫" width="380px" destroy-on-close>
      <el-radio-group v-model="moveTargetKbId" style="display:flex;flex-direction:column;gap:10px;">
        <el-radio :label="null">
          <span>&#x1F4CB; 未分類</span>
        </el-radio>
        <el-radio v-for="kb in kbs" :key="kb.id" :label="kb.id">
          <span>{{ kb.icon }} {{ kb.name }}</span>
        </el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="showMoveDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmMove" :loading="moving">確認移動</el-button>
      </template>
    </el-dialog>

    <!-- 新增標籤 Dialog -->
    <el-dialog v-model="showNewTagDialog" title="新增標籤" width="360px" destroy-on-close>
      <el-form @submit.prevent label-width="70px">
        <el-form-item label="標籤名稱">
          <el-input v-model="newTagForm.name" placeholder="輸入標籤名稱" maxlength="30" show-word-limit autofocus />
        </el-form-item>
        <el-form-item label="顏色">
          <el-color-picker v-model="newTagForm.color" show-alpha />
          <span style="margin-left:8px;font-size:13px;color:#606266;">{{ newTagForm.color }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showNewTagDialog = false">取消</el-button>
        <el-button type="primary" :loading="newTagSaving" @click="createTag">建立</el-button>
      </template>
    </el-dialog>

    <!-- 匯入連結結果 Dialog -->
    <el-dialog
      v-model="importResultDialog.show"
      title="匯入連結結果"
      width="620px"
      :close-on-click-modal="false"
      @closed="loadDocs"
    >
      <div class="import-result-summary">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="總計">{{ importResultDialog.total }} 筆</el-descriptions-item>
          <el-descriptions-item label="已排入處理">
            <el-text type="success">{{ importResultDialog.queued }} 筆</el-text>
          </el-descriptions-item>
          <el-descriptions-item label="跳過">
            <el-text type="warning">{{ importResultDialog.skipped }} 筆</el-text>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <div v-if="importResultDialog.skippedItems.length > 0" style="margin-top:16px;">
        <div style="font-size:13px;color:#64748b;margin-bottom:8px;">以下連結已跳過：</div>
        <el-table
          :data="importResultDialog.skippedItems"
          size="small"
          border
          max-height="280"
          style="width:100%"
        >
          <el-table-column prop="srl" label="序號" width="64" align="center" />
          <el-table-column prop="title" label="標題" min-width="200" show-overflow-tooltip />
          <el-table-column prop="reason" label="原因" width="180" />
        </el-table>
      </div>
      <template #footer>
        <el-button type="primary" @click="importResultDialog.show = false">確定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated, onUnmounted, watch, nextTick } from 'vue'
import {
  Upload, Link, LayoutGrid, List, Share2, Trash2, Search, Plus, Tag,
  CheckSquare, X, Settings2, Check, MoreHorizontal, FolderInput, RefreshCw,
  Eye, Loader2, FileText, FileSpreadsheet, Globe, ChevronRight, ChevronDown,
  Database, FileStack, Copy, Zap, SendHorizontal
} from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { docsApi, kbApi, tagsApi, wikiApi } from '../api/index.js'

const pageSize = ref(25)
const CHUNK_PAGE_SIZE = 50
const COLOR_PRESETS = [
  '#2563eb', '#7c3aed', '#db2777', '#dc2626',
  '#ea580c', '#ca8a04', '#16a34a', '#0891b2',
  '#64748b', '#1e293b',
]
const viewModes = [
  { value: 'grid', label: 'Grid 卡片', icon: LayoutGrid },
  { value: 'table', label: '表格', icon: List },
  { value: 'node', label: '節點圖', icon: Share2 },
]

const kbs = ref([])
const selectedKbId = ref(null)
const selectedKb = computed(() => kbs.value.find(k => k.id === selectedKbId.value) || null)
const totalDocCount = ref(0)

// KB 展開樹狀
 const expandedKbs = ref(new Set())
const kbDocs = ref({})       // { [kb.id]: doc[] }
const kbDocsLoading = ref(new Set())

async function toggleKbExpand(kbId) {
  if (expandedKbs.value.has(kbId)) {
    expandedKbs.value = new Set([...expandedKbs.value].filter(id => id !== kbId))
    return
  }
  const next = new Set(expandedKbs.value)
  next.add(kbId)
  expandedKbs.value = next
  if (!kbDocs.value[kbId]) {
    kbDocsLoading.value = new Set([...kbDocsLoading.value, kbId])
    try {
      const res = await docsApi.list({ kb_id: kbId, limit: 50 })
      const list = Array.isArray(res) ? res : (res?.items || res?.documents || [])
      kbDocs.value = { ...kbDocs.value, [kbId]: list }
    } catch {}
    kbDocsLoading.value = new Set([...kbDocsLoading.value].filter(id => id !== kbId))
  }
}

function selectDocFromKb(kbId, doc) {
  selectKb(kbId)
}

// ── 拖曳到 KB ────────────────────────────────────────────
const draggingDocId = ref(null)
const dragOverKbId  = ref(null)

async function onDocDrop(kbId) {
  dragOverKbId.value = null
  const docId = draggingDocId.value
  draggingDocId.value = null
  if (!docId || !kbId) return
  try {
    await docsApi.moveToKb(docId, kbId)
    ElMessage.success('已移入知識庫')
    loadDocs()
    await loadKbs()
    // 刷新該 KB 的展開列表快取
    const updated = { ...kbDocs.value }
    delete updated[kbId]
    kbDocs.value = updated
  } catch (e) {
    ElMessage.error('移動失敗：' + (e.message || ''))
  }
}

const docs = ref([])
const loading = ref(false)
const selectedDocs = ref(new Set()) // 批次選取的 doc_id Set
const batchDeleting = ref(false)
const isSelectMode = ref(false)

function handleSelectCommand(command) {
  if (command === 'all') {
    toggleSelectAll(true)
    isSelectMode.value = true
  } else {
    toggleSelectAll(false)
    isSelectMode.value = false
  }
}

// 垃圾桶模式
const trashMode = ref(false)
const trashDocs = ref([])
const trashLoading = ref(false)
const trashTotal = ref(0)
const batchRestoring = ref(false)
const batchPermanentDeleting = ref(false)
const emptyingTrash = ref(false)

// 層面²2：文件卡片 tag chip 批次選取
const selectedChipTags = ref(new Set()) // Set of tag names
const chipTagWorking = ref(false)

function toggleChipTag(tagName) {
  const s = new Set(selectedChipTags.value)
  if (s.has(tagName)) s.delete(tagName)
  else s.add(tagName)
  selectedChipTags.value = s
}

async function batchChipTagRemove() {
  const tagNames = [...selectedChipTags.value]
  const docIds = [...selectedDocs.value]
  if (!tagNames.length || !docIds.length) return
  chipTagWorking.value = true
  let failCount = 0
  for (const tagName of tagNames) {
    const tag = tags.value.find(t => t.name === tagName)
    if (!tag) continue
    for (const docId of docIds) {
      const doc = docs.value.find(d => d.doc_id === docId)
      if (!doc || !doc.tags.includes(tagName)) continue
      try { await tagsApi.removeFromDoc(tag.id, docId) }
      catch { failCount++ }
    }
  }
  chipTagWorking.value = false
  selectedChipTags.value = new Set()
  if (failCount > 0) ElMessage.error(`${failCount} 筆失敗`)
  else ElMessage.success(`已從選取文件移除標籤`)
  await loadDocs()
}

async function batchChipTagApply() {
  const tagNames = [...selectedChipTags.value]
  const docIds = [...selectedDocs.value]
  if (!tagNames.length || !docIds.length) return
  chipTagWorking.value = true
  let failCount = 0
  for (const tagName of tagNames) {
    const tag = tags.value.find(t => t.name === tagName)
    if (!tag) continue
    for (const docId of docIds) {
      const doc = docs.value.find(d => d.doc_id === docId)
      if (!doc || doc.tags.includes(tagName)) continue
      try { await tagsApi.addToDoc(tag.id, docId) }
      catch { failCount++ }
    }
  }
  chipTagWorking.value = false
  selectedChipTags.value = new Set()
  if (failCount > 0) ElMessage.error(`${failCount} 筆失敗`)
  else ElMessage.success(`已套用標籤到選取文件`)
  await loadDocs()
}

const isAllSelected = computed(() => {
  if (trashMode.value) return trashDocs.value.length > 0 && trashDocs.value.every(d => selectedDocs.value.has(d.doc_id))
  return docs.value.length > 0 && docs.value.every(d => selectedDocs.value.has(d.doc_id))
})
const isIndeterminate = computed(() =>
  selectedDocs.value.size > 0 && !isAllSelected.value
)

function toggleSelectDoc(docId) {
  const s = new Set(selectedDocs.value)
  if (s.has(docId)) s.delete(docId)
  else s.add(docId)
  selectedDocs.value = s
  // 所有文件都取消選取時自動離開勾選模式
  if (selectedDocs.value.size === 0) isSelectMode.value = false
}

function handleCardClick(doc) {
  if (isSelectMode.value) {
    toggleSelectDoc(doc.doc_id)
  } else {
    openPanel(doc)
  }
}

function handleCheckboxClick(docId) {
  isSelectMode.value = true
  toggleSelectDoc(docId)
}

function toggleSelectAll(val) {
  if (val) {
    const source = trashMode.value ? trashDocs.value : docs.value
    selectedDocs.value = new Set(source.map(d => d.doc_id))
    isSelectMode.value = true
  } else {
    selectedDocs.value = new Set()
    isSelectMode.value = false
  }
}

function clearSelection() {
  selectedDocs.value = new Set()
  isSelectMode.value = false
  selectedChipTags.value = new Set()
}
const page = ref(1)
const total = ref(0)

const viewMode = ref('grid')

const uploading = ref(false)
const uploadError = ref('')
const uploadSuccess = ref(false)

const searchQuery = ref('')
const searchMode = ref(false)
const searching = ref(false)
const searchResults = ref([])
const lastQuery = ref('')
const aiSearchEnabled = ref(true)
const filteredDocs = ref([])

const displayedDocs = computed(() => {
  if (!aiSearchEnabled.value && searchQuery.value.trim()) return filteredDocs.value
  return docs.value
})

const panelDoc = ref(null)
const panelTab = ref('info')
const panelRef = ref(null)
const panelOpen = ref(false)
const panelWidth = ref(380)
const PANEL_MIN_W = 280
const PANEL_MAX_W = 1200
const PANEL_DEFAULT_W = 380

function autoFitPanelWidth() {
  // 暫時撐到最大寬度測量，再收縮到實際所需
  panelWidth.value = PANEL_MAX_W
  nextTick(() => {
    requestAnimationFrame(() => {
      const el = panelRef.value
      if (!el) return
      const table = el.querySelector('.sheet-table')
      if (!table) return
      const need = table.offsetWidth + 48
      panelWidth.value = Math.min(PANEL_MAX_W, Math.max(PANEL_MIN_W, need))
    })
  })
}

function onPanelResizeStart(e) {
  const startX = e.clientX
  const startW = panelWidth.value
  const onMove = (ev) => {
    const delta = startX - ev.clientX
    panelWidth.value = Math.min(PANEL_MAX_W, Math.max(PANEL_MIN_W, startW + delta))
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}
const editForm = ref({ title: '', description: '', notes: '', icon: '' })
const editSaving = ref(false)
const reanalyzing = ref(false)
const chunks = ref([])
const chunksTotal = ref(0)
const chunkPage = ref(1)
const chunksLoading = ref(false)
const fullContent = ref('')
const contentLoading = ref(false)
const contentLoaded = ref(false)
const contentExpanded = ref(false)
const sheetExpanded = ref(false)

// 試算表
const sheetLoading = ref(false)
const sheetError = ref('')
const sheetNames = ref([])
const sheetHtml = ref({})
const activeSheet = ref('')

const cyContainer = ref(null)
const cyLoading = ref(false)
let cyInstance = null

const showKbDialog = ref(false)
const editKb = ref(null)
const kbSaving = ref(false)
const kbForm = ref({
  name: '', icon: '📚', color: '#2563eb', description: '',
  embedding_model: '', embedding_provider: 'ollama',
  chunk_size: null, language: 'auto',
  rerank_enabled: null, default_top_k: null,
})
const showKbAdvanced = ref(false)
const embeddingModels = ref([])

const showMoveDialog = ref(false)
const moveTargetDoc = ref(null)
const moveTargetKbId = ref(null)
const moving = ref(false)

// 匯入連結
const importInputRef = ref(null)
const importing = ref(false)
const importResultDialog = ref({
  show: false,
  total: 0,
  queued: 0,
  skipped: 0,
  skippedItems: [],
})

// Tags
const tags = ref([])
const selectedTagId = ref(null)

// Tag 批次管理
const tagManageMode = ref(false)
const selectedTagIds = ref(new Set())
const tagBatchWorking = ref(false)

const isAllTagsSelected = computed(() => tags.value.length > 0 && selectedTagIds.value.size === tags.value.length)
const isTagsIndeterminate = computed(() => selectedTagIds.value.size > 0 && !isAllTagsSelected.value)

function toggleSelectAllTags() {
  if (isAllTagsSelected.value) {
    selectedTagIds.value = new Set()
  } else {
    selectedTagIds.value = new Set(tags.value.map(t => t.id))
  }
}

function toggleTagManage() {
  tagManageMode.value = !tagManageMode.value
  selectedTagIds.value = new Set()
}

function toggleTagSelection(tagId) {
  const s = new Set(selectedTagIds.value)
  if (s.has(tagId)) s.delete(tagId)
  else s.add(tagId)
  selectedTagIds.value = s
}

async function batchTagRemoveAll() {
  const ids = [...selectedTagIds.value]
  if (!ids.length) return
  const names = tags.value.filter(t => ids.includes(t.id)).map(t => t.name).join('、')
  try {
    await ElMessageBox.confirm(
      `確定從所有文件移除 ${ids.length} 個標籤（${names}）？標籤本身保留。`,
      '批次移除關聯',
      { type: 'warning', confirmButtonText: '確定', cancelButtonText: '取消' }
    )
  } catch { return }
  tagBatchWorking.value = true
  let failCount = 0
  for (const id of ids) {
    try { await tagsApi.removeFromAll(id) }
    catch { failCount++ }
  }
  tagBatchWorking.value = false
  selectedTagIds.value = new Set()
  tagManageMode.value = false
  if (failCount > 0) ElMessage.error(`${failCount} 個標籤移除失敗`)
  else ElMessage.success(`已從所有文件移除 ${ids.length} 個標籤`)
  await loadTags()
  await loadDocs()
}

async function batchTagDelete() {
  const ids = [...selectedTagIds.value]
  if (!ids.length) return
  const names = tags.value.filter(t => ids.includes(t.id)).map(t => t.name).join('、')
  try {
    await ElMessageBox.confirm(
      `確定永久刪除 ${ids.length} 個標籤（${names}）？此操作不可復原。`,
      '批次刪除標籤',
      { type: 'warning', confirmButtonText: `確定刪除 ${ids.length} 個`, cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
  } catch { return }
  tagBatchWorking.value = true
  let failCount = 0
  for (const id of ids) {
    try {
      await tagsApi.delete(id)
      if (selectedTagId.value === id) selectedTagId.value = null
    } catch { failCount++ }
  }
  tagBatchWorking.value = false
  selectedTagIds.value = new Set()
  tagManageMode.value = false
  if (failCount > 0) ElMessage.error(`${failCount} 個標籤刪除失敗`)
  else ElMessage.success(`已刪除 ${ids.length} 個標籤`)
  await loadTags()
  await loadDocs()
}

// 待審核操作狀態
const reviewConfirming = ref(false)
const reviewRejecting = ref(false)

// 新增標籤 dialog
const showNewTagDialog = ref(false)
const newTagForm = ref({ name: '', color: '#409eff' })
const newTagSaving = ref(false)

// 輪詢：追蹤處理中文件，完成時通知
let pollingTimer = null
const processingIds = ref(new Set())
const pendingReviews = ref([])   // [{doc_id, title, suggested_kb_id, suggested_kb_name, suggested_tags}]
const _seenReviewIds = new Set() // 已收集過的 doc_id，防止重複

function startPolling() {
  if (pollingTimer) return
  pollingTimer = setInterval(async () => {
    if (processingIds.value.size === 0) return
    try {
      const data = await docsApi.list({ limit: 100, offset: 0 })
      data.forEach(doc => {
        if (processingIds.value.has(doc.doc_id)) {
          if (doc.status === 'indexed') {
            ElMessage({ message: `✅ 「${doc.title}」已完成索引（${doc.chunk_count} chunks）`, type: 'success', duration: 5000 })
            processingIds.value.delete(doc.doc_id)
            const idx = docs.value.findIndex(d => d.doc_id === doc.doc_id)
            if (idx !== -1) docs.value[idx] = { ...docs.value[idx], status: doc.status, chunk_count: doc.chunk_count, suggested_kb_id: doc.suggested_kb_id, suggested_kb_name: doc.suggested_kb_name }
          } else if (doc.status === 'error') {
            ElMessage({ message: `❌ 「${doc.title}」處理失敗`, type: 'error', duration: 6000 })
            processingIds.value.delete(doc.doc_id)
            const idx = docs.value.findIndex(d => d.doc_id === doc.doc_id)
            if (idx !== -1) docs.value[idx] = { ...docs.value[idx], status: doc.status }
          }
        }
      })
      // 收集有建議的文件（KB 或 tag）進 pendingReviews
      for (const doc of data) {
        if (_seenReviewIds.has(doc.doc_id)) continue
        if (doc.status !== 'indexed') continue
        const hasKb = doc.suggested_kb_name && !doc.knowledge_base_id
        const hasTag = doc.suggested_tags && doc.suggested_tags.length > 0
        if (hasKb || hasTag) {
          _seenReviewIds.add(doc.doc_id)
          pendingReviews.value.push({
            doc_id: doc.doc_id,
            title: doc.title,
            suggested_kb_id: doc.suggested_kb_id || null,
            suggested_kb_name: doc.suggested_kb_name || null,
            suggested_tags: doc.suggested_tags || [],
          })
        }
      }
    } catch {}
  }, 5000)
}

let _docsMounting = false
onMounted(async () => {
  _docsMounting = true
  try {
    await loadKbs()
    await loadTags()
    await loadDocs()
    startPolling()
  } finally {
    _docsMounting = false
  }
  window.addEventListener('ai-action', _onAiAction)
})

onActivated(async () => {
  if (_docsMounting) return
  await loadKbs()
  await loadTags()
  await loadDocs()
})

onUnmounted(() => {
  if (cyInstance) { cyInstance.destroy(); cyInstance = null }
  if (pollingTimer) { clearInterval(pollingTimer); pollingTimer = null }
  window.removeEventListener('ai-action', _onAiAction)
})

function _onAiAction(e) {
  const action = e.detail
  if (action.type === 'create_kb') loadKbs()
  else if (action.type === 'delete_doc') loadDocs()
  else if (action.type === 'move_to_kb') { loadDocs(); loadKbs() }
  else if (action.type === 'reload_docs') { loadDocs(); loadKbs() }
  else if (action.type === 'search_docs') {
    searchQuery.value = action.query || ''
    // 觸發搜尋（若有搜尋模式切換邏輯在這裡觸發）
    if (searchQuery.value) loadDocs()
  }
}

async function loadKbs() {
  try {
    kbs.value = await kbApi.list()
  } catch (e) {
    console.error('loadKbs list error:', e)
  }
  try {
    const result = await docsApi.count()
    totalDocCount.value = result.total ?? 0
  } catch (e) {
    console.error('loadKbs count error:', e)
  }
}

async function loadTags() {
  try {
    tags.value = await tagsApi.list()
  } catch (e) {
    console.error(e)
  }
}

// ── 標籤側欄右鍵選單 ────────────────────────────────────────────────────────
async function handleTagSidebarCommand(cmd, tag) {
  if (cmd === 'removeAll') {
    try {
      await ElMessageBox.confirm(
        `確定要從所有文件移除標籤「${tag.name}」嗎？標籤本身保留。`,
        '從所有文件移除',
        { type: 'warning', confirmButtonText: '確定', cancelButtonText: '取消' }
      )
      const res = await tagsApi.removeFromAll(tag.id)
      ElMessage.success(`已從 ${res.removed_doc_count ?? 0} 篇文件移除標籤`)
      await loadTags()
      await loadDocs()
    } catch {}
  } else if (cmd === 'deleteTag') {
    try {
      await ElMessageBox.confirm(
        `「${tag.name}」將從 ${tag.doc_count ?? '?'} 篇文件移除並永久刪除，確定嗎？`,
        '徹底刪除標籤',
        { type: 'warning', confirmButtonText: '確定刪除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
      )
      await tagsApi.delete(tag.id)
      ElMessage.success(`標籤「${tag.name}」已刪除`)
      if (selectedTagId.value === tag.id) selectedTagId.value = null
      await loadTags()
      await loadDocs()
    } catch {}
  }
}

// ── 新增標籤 ────────────────────────────────────────────────────────────────
async function createTag() {
  if (!newTagForm.value.name.trim()) {
    ElMessage.warning('請輸入標籤名稱')
    return
  }
  newTagSaving.value = true
  try {
    await tagsApi.create(newTagForm.value.name.trim(), newTagForm.value.color)
    ElMessage.success('標籤已建立')
    showNewTagDialog.value = false
    newTagForm.value = { name: '', color: '#409eff' }
    await loadTags()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    newTagSaving.value = false
  }
}

// ── 待審核批次操作 ──────────────────────────────────────────────────────────
async function confirmAllReviews() {
  reviewConfirming.value = true
  try {
    for (const r of pendingReviews.value) {
      try {
        if (r.suggested_kb_name && r.suggested_kb_id) {
          await docsApi.confirmKbs(r.doc_id, 'confirm', [r.suggested_kb_id])
        }
        if (r.suggested_tags && r.suggested_tags.length > 0) {
          const tagIds = r.suggested_tags.map(t => t.tag_id).filter(Boolean)
          await docsApi.confirmTagSuggestions(r.doc_id, 'confirm', tagIds)
        }
      } catch {}
    }
    pendingReviews.value = []
    ElMessage.success('已全部確認')
    await loadTags()
    await loadDocs()
  } finally {
    reviewConfirming.value = false
  }
}

async function rejectAllReviews() {
  reviewRejecting.value = true
  try {
    for (const r of pendingReviews.value) {
      try {
        if (r.suggested_kb_name) {
          await docsApi.confirmKbs(r.doc_id, 'reject', [])
        }
        if (r.suggested_tags && r.suggested_tags.length > 0) {
          await docsApi.confirmTagSuggestions(r.doc_id, 'reject', [])
        }
      } catch {}
    }
    pendingReviews.value = []
    ElMessage.success('已全部拒絕')
    await loadDocs()
  } finally {
    reviewRejecting.value = false
  }
}

function selectTag(id) {
  selectedTagId.value = selectedTagId.value === id ? null : id
  page.value = 1
  searchMode.value = false
  loadDocs()
}

function getTagStyle(tagName) {
  const tag = tags.value.find(t => t.name === tagName)
  if (!tag) return {}
  return { background: tag.color + '22', borderColor: tag.color, color: tag.color }
}

function getTagColorStyle(tag) {
  return { background: tag.color + '22', borderColor: tag.color, color: tag.color }
}

async function toggleTagOnDoc(tag, doc) {
  try {
    if (doc.tags.includes(tag.name)) {
      await tagsApi.removeFromDoc(tag.id, doc.doc_id)
      doc.tags = doc.tags.filter(t => t !== tag.name)
    } else {
      await tagsApi.addToDoc(tag.id, doc.doc_id)
      if (!doc.tags.includes(tag.name)) doc.tags = [...doc.tags, tag.name]
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function removeTagFromDocByName(tagName, doc) {
  const tag = tags.value.find(t => t.name === tagName)
  if (!tag) return
  await toggleTagOnDoc(tag, doc)
}

function selectKb(id) {
  trashMode.value = false
  selectedDocs.value = new Set()
  selectedKbId.value = id
  selectedTagId.value = null
  page.value = 1
  searchMode.value = false
  loadDocs()
}

function selectTrash() {
  trashMode.value = true
  selectedDocs.value = new Set()
  selectedKbId.value = null
  selectedTagId.value = null
  searchMode.value = false
  loadTrash()
}

async function loadTrash() {
  trashLoading.value = true
  try {
    const data = await docsApi.trash({ limit: 200 })
    trashDocs.value = Array.isArray(data) ? data : []
    trashTotal.value = trashDocs.value.length
  } catch (e) {
    ElMessage.error('載入垃圾桶失敗：' + e.message)
  } finally {
    trashLoading.value = false
  }
}

async function restoreDoc(docId) {
  try {
    await docsApi.restore(docId)
    ElMessage.success('文件已還原')
    trashDocs.value = trashDocs.value.filter(d => d.doc_id !== docId)
    trashTotal.value = trashDocs.value.length
    selectedDocs.value = new Set([...selectedDocs.value].filter(id => id !== docId))
    await loadKbs()
  } catch (e) {
    ElMessage.error('還原失敗：' + e.message)
  }
}

async function permanentDeleteDoc(docId) {
  try {
    await ElMessageBox.confirm('永久刪除後無法復原，確定繼續？', '永久刪除', {
      type: 'warning', confirmButtonText: '永久刪除', cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger',
    })
    await docsApi.permanentDelete(docId)
    // 同時從兩個視圖移除（無論從哪裡觸發）
    docs.value = docs.value.filter(d => d.doc_id !== docId)
    total.value = Math.max(0, total.value - 1)
    trashDocs.value = trashDocs.value.filter(d => d.doc_id !== docId)
    trashTotal.value = trashDocs.value.length
    selectedDocs.value = new Set([...selectedDocs.value].filter(id => id !== docId))
    if (panelDoc.value?.doc_id === docId) closePanel()
    ElMessage.success('已永久刪除')
    loadKbs()
  } catch {}
}

async function restoreSelected() {
  const ids = [...selectedDocs.value]
  if (!ids.length) return
  batchRestoring.value = true
  let failCount = 0
  for (const id of ids) {
    try { await docsApi.restore(id) }
    catch { failCount++ }
  }
  batchRestoring.value = false
  selectedDocs.value = new Set()
  if (failCount > 0) ElMessage.error(`${failCount} 篇還原失敗`)
  else ElMessage.success(`已還原 ${ids.length} 篇文件`)
  await loadTrash()
  await loadKbs()
}

async function permanentDeleteSelected() {
  const ids = [...selectedDocs.value]
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(
      `永久刪除 ${ids.length} 篇文件？此操作不可復原。`,
      '批次永久刪除',
      { type: 'warning', confirmButtonText: `永久刪除 ${ids.length} 篇`, cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
  } catch { return }
  batchPermanentDeleting.value = true
  let failCount = 0
  for (const id of ids) {
    try { await docsApi.permanentDelete(id) }
    catch { failCount++ }
  }
  batchPermanentDeleting.value = false
  selectedDocs.value = new Set()
  if (failCount > 0) ElMessage.error(`${failCount} 篇刪除失敗`)
  else ElMessage.success(`已永久刪除 ${ids.length} 篇文件`)
  await loadTrash()
}

async function emptyTrash() {
  if (trashDocs.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `清空垃圾桶將永久刪除 ${trashDocs.value.length} 篇文件，此操作不可復原。`,
      '清空垃圾桶',
      { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
  } catch { return }
  emptyingTrash.value = true
  const ids = trashDocs.value.map(d => d.doc_id)
  let failCount = 0
  for (const id of ids) {
    try { await docsApi.permanentDelete(id) }
    catch { failCount++ }
  }
  emptyingTrash.value = false
  if (failCount > 0) ElMessage.error(`${failCount} 篇刪除失敗`)
  else ElMessage.success('垃圾桶已清空')
  await loadTrash()
}

function openKbDialog(kb) {
  editKb.value = kb
  if (kb) {
    kbForm.value = {
      name: kb.name, icon: kb.icon, color: kb.color, description: kb.description || '',
      embedding_model: kb.embedding_model || '',
      embedding_provider: kb.embedding_provider || 'ollama',
      chunk_size: kb.chunk_size ?? null,
      language: kb.language || 'auto',
      rerank_enabled: kb.rerank_enabled ?? null,
      default_top_k: kb.default_top_k ?? null,
    }
  } else {
    kbForm.value = {
      name: '', icon: '📚', color: '#2563eb', description: '',
      embedding_model: '', embedding_provider: 'ollama',
      chunk_size: null, language: 'auto',
      rerank_enabled: null, default_top_k: null,
    }
  }
  showKbAdvanced.value = false
  showKbDialog.value = true
  loadEmbeddingModels()
}

async function loadEmbeddingModels() {
  try {
    const list = await wikiApi.list()
    embeddingModels.value = (list || []).filter(m => m.model_type === 'embedding')
  } catch (e) {
    embeddingModels.value = []
  }
}

function onEmbeddingChange(name) {
  if (!name) {
    kbForm.value.embedding_provider = 'ollama'
    return
  }
  const m = embeddingModels.value.find(x => x.name === name)
  if (m) kbForm.value.embedding_provider = m.provider || 'ollama'
}

async function saveKb() {
  if (!kbForm.value.name.trim()) return ElMessage.warning('請輸入知識庫名稱')
  kbSaving.value = true
  try {
    if (editKb.value) {
      await kbApi.update(editKb.value.id, kbForm.value)
    } else {
      await kbApi.create(kbForm.value)
    }
    showKbDialog.value = false
    await loadKbs()
    ElMessage.success(editKb.value ? '更新成功' : '知識庫建立成功')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    kbSaving.value = false
  }
}

async function handleKbCommand(cmd, kb) {
  if (cmd === 'edit') {
    openKbDialog(kb)
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(
        `確定刪除知識庫「${kb.name}」？文件不會被刪除，但會移出此知識庫。`,
        '刪除知識庫',
        { type: 'warning', confirmButtonText: '確定刪除', cancelButtonText: '取消' }
      )
      await kbApi.delete(kb.id)
      if (selectedKbId.value === kb.id) selectedKbId.value = null
      await loadKbs()
      await loadDocs()
      ElMessage.success('知識庫已刪除')
    } catch {}
  }
}

async function loadDocs() {
  loading.value = true
  try {
    const params = { limit: pageSize.value, offset: (page.value - 1) * pageSize.value }
    const countParams = {}
    if (selectedKbId.value) { params.kb_id = selectedKbId.value; countParams.kb_id = selectedKbId.value }
    if (selectedTagId.value) { params.tag_id = selectedTagId.value; countParams.tag_id = selectedTagId.value }
    const [data, countResult] = await Promise.all([
      docsApi.list(params),
      docsApi.count(countParams),
    ])
    docs.value = data
    total.value = countResult.total ?? 0
    // 全部文件（無篩選）時同步更新 sidebar 計數
    if (!selectedKbId.value && !selectedTagId.value) {
      totalDocCount.value = countResult.total ?? 0
    }
    // 把仍在處理中的文件加入輪詢清單
    data.forEach(doc => {
      if (doc.status === 'processing' || doc.status === 'pending') {
        processingIds.value.add(doc.doc_id)
      }
    })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function handlePageSizeChange() {
  page.value = 1
  loadDocs()
}

async function handleUpload({ file }) {
  uploading.value = true
  uploadError.value = ''
  uploadSuccess.value = false
  try {
    await docsApi.upload(file, selectedKbId.value)
    uploadSuccess.value = true
    await loadKbs()
    await loadDocs()
  } catch (e) {
    uploadError.value = e.message
  } finally {
    uploading.value = false
  }
}

async function handleImportExcel(event) {
  const file = event.target.files?.[0]
  if (!event.target) return
  event.target.value = ''   // 讓同一個檔案可再次選取
  if (!file) return

  importing.value = true
  try {
    const result = await docsApi.importExcel(file, selectedKbId.value)
    importResultDialog.value = {
      show: true,
      total: result.total ?? 0,
      queued: result.queued ?? 0,
      skipped: result.skipped ?? 0,
      skippedItems: result.skipped_items ?? [],
    }
    // 將剛排入的文件加入輪詢追蹤
    if (result.doc_ids?.length) {
      result.doc_ids.forEach(id => processingIds.value.add(id))
    }
    await loadKbs()
  } catch (e) {
    ElMessage.error(`匯入失敗：${e.message}`)
  } finally {
    importing.value = false
  }
}

async function deleteDoc(docId) {
  try {
    await ElMessageBox.confirm('文件將移入垃圾桶，可於垃圾桶中還原。', '刪除文件', {
      type: 'warning', confirmButtonText: '確定刪除', cancelButtonText: '取消',
    })
    await docsApi.delete(docId)
    // 樂觀更新：立即從本地移除，不等 API 重新拉取
    docs.value = docs.value.filter(d => d.doc_id !== docId)
    total.value = Math.max(0, total.value - 1)
    selectedDocs.value = new Set([...selectedDocs.value].filter(id => id !== docId))
    if (panelDoc.value?.doc_id === docId) closePanel()
    ElMessage.success('文件已刪除')
    // 背景靜默同步
    loadKbs()
    loadDocs()
  } catch {}
}

async function deleteSelected() {
  const ids = [...selectedDocs.value]
  if (ids.length === 0) return
  try {
    await ElMessageBox.confirm(
      `${ids.length} 篇文件將移入垃圾桶，可於垃圾桶中還原。`,
      '批次刪除',
      { type: 'warning', confirmButtonText: `移入垃圾桶 ${ids.length} 篇`, cancelButtonText: '取消' }
    )
  } catch { return }

  batchDeleting.value = true
  let failCount = 0
  const firstError = { msg: '' }
  for (const id of ids) {
    try {
      await docsApi.delete(id)
      if (panelDoc.value?.doc_id === id) closePanel()
    } catch (err) {
      console.error('[deleteSelected] id:', id, 'error:', err?.message ?? err)
      if (!firstError.msg) firstError.msg = err?.message ?? String(err)
      failCount++
    }
  }
  batchDeleting.value = false
  selectedDocs.value = new Set()

  if (failCount > 0) ElMessage.error(`${failCount} 篇刪除失敗`)
  else ElMessage.success(`已刪除 ${ids.length} 篇文件`)

  await loadKbs()
  await loadDocs()
}

function handleDocCommand(cmd, doc) {
  if (cmd === 'detail') openPanel(doc)
  else if (cmd === 'move') openMoveDialog(doc)
  else if (cmd === 'delete') deleteDoc(doc.doc_id)
  else if (cmd === 'permanent-delete') permanentDeleteDoc(doc.doc_id)
}

function switchView(mode) {
  viewMode.value = mode
  if (mode === 'node') {
    nextTick(() => initCytoscape())
  } else {
    if (cyInstance) { cyInstance.destroy(); cyInstance = null }
  }
}

async function doAiSearch() {
  if (!searchQuery.value.trim()) return
  searching.value = true
  searchMode.value = true
  lastQuery.value = searchQuery.value
  searchResults.value = []
  try {
    searchResults.value = await docsApi.aiSearch(searchQuery.value, selectedKbId.value)
  } catch (e) {
    ElMessage.error('搜尋失敗：' + e.message)
  } finally {
    searching.value = false
  }
}

function doSearch() {
  if (!searchQuery.value.trim()) return
  if (aiSearchEnabled.value) {
    doAiSearch()
  } else {
    const q = searchQuery.value.trim().toLowerCase()
    filteredDocs.value = docs.value.filter(d =>
      (d.title || '').toLowerCase().includes(q)
    )
  }
}

function clearSearch() {
  searchMode.value = false
  searchQuery.value = ''
  searchResults.value = []
}

function syncEditForm(doc) {
  editForm.value = {
    title: doc.title || '',
    description: doc.custom_fields?.description || '',
    notes: doc.custom_fields?.notes || '',
    icon: doc.custom_fields?.icon || '',
  }
}

function openPanel(doc) {
  panelDoc.value = doc
  panelTab.value = 'info'
  panelWidth.value = PANEL_DEFAULT_W
  chunks.value = []
  chunksTotal.value = 0
  fullContent.value = ''
  contentLoaded.value = false
  contentExpanded.value = false
  sheetExpanded.value = false
  sheetNames.value = []
  sheetHtml.value = {}
  activeSheet.value = ''
  sheetError.value = ''
  syncEditForm(doc)
  nextTick(() => { panelOpen.value = true })
}

function openPanelById(docId, partialDoc) {
  panelDoc.value = { ...partialDoc, doc_id: docId }
  panelTab.value = 'info'
  panelWidth.value = PANEL_DEFAULT_W
  chunks.value = []
  chunksTotal.value = 0
  fullContent.value = ''
  contentLoaded.value = false
  contentExpanded.value = false
  sheetExpanded.value = false
  sheetNames.value = []
  sheetHtml.value = {}
  activeSheet.value = ''
  sheetError.value = ''
  syncEditForm(partialDoc)
  nextTick(() => { panelOpen.value = true })
}

function closePanel() {
  panelOpen.value = false
  // 等動畫結束後再清除資料
  setTimeout(() => {
    if (!panelOpen.value) panelDoc.value = null
  }, 320)
}

function toggleContentExpand() {
  contentExpanded.value = !contentExpanded.value
  if (contentExpanded.value && !contentLoaded.value) {
    loadFullContent()
  }
}

function toggleSheetExpand() {
  sheetExpanded.value = !sheetExpanded.value
  if (sheetExpanded.value && sheetNames.value.length === 0) {
    loadSheet()
  }
}

function copySourceUrl(url) {
  navigator.clipboard.writeText(url).then(() => {
    ElMessage.success('連結已複製')
  })
}

async function saveDocMeta() {
  if (!panelDoc.value) return
  editSaving.value = true
  try {
    const res = await docsApi.updateMeta(panelDoc.value.doc_id, {
      title: editForm.value.title,
      description: editForm.value.description,
      notes: editForm.value.notes,
      icon: editForm.value.icon,
    })
    // 更新本地資料
    panelDoc.value.title = res.title
    panelDoc.value.custom_fields = res.custom_fields
    const idx = docs.value.findIndex(d => d.doc_id === panelDoc.value.doc_id)
    if (idx !== -1) docs.value[idx] = { ...docs.value[idx], title: res.title, custom_fields: res.custom_fields }
    ElMessage.success('儲存成功')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    editSaving.value = false
  }
}

async function reanalyzeDoc() {
  if (!panelDoc.value) return
  try {
    await ElMessageBox.confirm(
      '重新分析會刪除現有 Chunks 並重新嵌入，確定繼續？',
      '重新 AI 分析',
      { type: 'warning', confirmButtonText: '確定', cancelButtonText: '取消' }
    )
    reanalyzing.value = true
    await docsApi.reanalyze(panelDoc.value.doc_id)
    panelDoc.value.status = 'pending'
    const idx = docs.value.findIndex(d => d.doc_id === panelDoc.value.doc_id)
    if (idx !== -1) docs.value[idx] = { ...docs.value[idx], status: 'pending' }
    ElMessage.success('已重新觸發分析')
  } catch {} finally {
    reanalyzing.value = false
  }
}

async function onPanelTabChange() {
  if (!panelDoc.value) return
  const paneName = panelTab.value
  if (paneName === 'chunks' && chunks.value.length === 0) {
    await loadChunks()
  }
}

watch(panelTab, (newTab) => {
  if (!panelDoc.value) return
  if (newTab === 'chunks' && chunks.value.length === 0) {
    loadChunks()
  }
})

// 切換工作表時重新適配面板寬度
watch(activeSheet, () => { autoFitPanelWidth() })

async function loadChunks() {
  if (!panelDoc.value) return
  chunksLoading.value = true
  try {
    const res = await docsApi.getChunks(panelDoc.value.doc_id, {
      limit: CHUNK_PAGE_SIZE,
      offset: (chunkPage.value - 1) * CHUNK_PAGE_SIZE,
    })
    chunks.value = res.chunks || []
    chunksTotal.value = res.total || 0
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    chunksLoading.value = false
  }
}

async function loadFullContent() {
  if (!panelDoc.value) return
  contentLoading.value = true
  try {
    const res = await docsApi.getChunks(panelDoc.value.doc_id, { limit: 200, offset: 0 })
    fullContent.value = (res.chunks || []).map(c => c.content).join('\n\n---\n\n')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    contentLoading.value = false
    contentLoaded.value = true
  }
}

async function loadSheet() {
  if (!panelDoc.value) return
  sheetLoading.value = true
  sheetError.value = ''
  try {
    const XLSX = window.XLSX
    if (!XLSX) throw new Error('試算表解析器尚未載入，請重新整理頁面')
    const arrayBuffer = await docsApi.download(panelDoc.value.doc_id)
    const workbook = XLSX.read(arrayBuffer, { type: 'array' })
    sheetNames.value = workbook.SheetNames
    activeSheet.value = workbook.SheetNames[0]
    const htmlMap = {}
    workbook.SheetNames.forEach(name => {
      htmlMap[name] = XLSX.utils.sheet_to_html(workbook.Sheets[name], { header: '', footer: '' })
        // 移除 SheetJS 自帶的 <html><body> 包裝，只保留 <table>...</table>
        .replace(/^[\s\S]*?(<table[\s\S]*<\/table>)[\s\S]*$/, '$1')
    })
    sheetHtml.value = htmlMap
  } catch (e) {
    sheetError.value = e.message || '無法載入試算表'
  } finally {
    sheetLoading.value = false
    autoFitPanelWidth()
  }
}

function openMoveDialog(doc) {
  moveTargetDoc.value = doc
  moveTargetKbId.value = doc.knowledge_base_id || null
  showMoveDialog.value = true
}

async function confirmMove() {
  if (!moveTargetDoc.value) return
  moving.value = true
  try {
    await docsApi.moveToKb(moveTargetDoc.value.doc_id, moveTargetKbId.value)
    showMoveDialog.value = false
    await loadKbs()
    await loadDocs()
    if (panelDoc.value?.doc_id === moveTargetDoc.value.doc_id) {
      const updated = docs.value.find(d => d.doc_id === moveTargetDoc.value.doc_id)
      if (updated) panelDoc.value = updated
    }
    ElMessage.success('文件已移動')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    moving.value = false
  }
}

async function initCytoscape() {
  if (!cyContainer.value || docs.value.length === 0) return
  cyLoading.value = true
  try {
    const cytoscape = (await import('cytoscape')).default
    if (cyInstance) { cyInstance.destroy(); cyInstance = null }

    const elements = []
    kbs.value.forEach(kb => {
      elements.push({
        data: { id: `kb-${kb.id}`, label: `${kb.icon} ${kb.name}`, kbColor: kb.color },
        classes: 'kb-parent',
      })
    })
    elements.push({
      data: { id: 'kb-none', label: '未分類', kbColor: '#94a3b8' },
      classes: 'kb-parent',
    })
    docs.value.forEach(doc => {
      const parentId = doc.knowledge_base_id ? `kb-${doc.knowledge_base_id}` : 'kb-none'
      const kbColor = doc.knowledge_base_id
        ? (kbs.value.find(k => k.id === doc.knowledge_base_id)?.color || '#2563eb')
        : '#94a3b8'
      elements.push({
        data: {
          id: doc.doc_id,
          label: doc.title.length > 16 ? doc.title.slice(0, 15) + '...' : doc.title,
          parent: parentId,
          kbColor,
          doc,
        },
        classes: `doc-node status-${doc.status}`,
      })
    })

    cyInstance = cytoscape({
      container: cyContainer.value,
      elements,
      style: [
        {
          selector: '.kb-parent',
          style: {
            'background-color': 'data(kbColor)',
            'background-opacity': 0.07,
            'border-width': 2,
            'border-color': 'data(kbColor)',
            'border-opacity': 0.5,
            label: 'data(label)',
            'text-valign': 'top',
            'text-halign': 'center',
            'font-size': '13px',
            'font-weight': 600,
            color: '#1e293b',
            'text-margin-y': -6,
          },
        },
        {
          selector: '.doc-node',
          style: {
            'background-color': 'data(kbColor)',
            'background-opacity': 0.85,
            label: 'data(label)',
            color: '#1e293b',
            'font-size': '10px',
            'text-wrap': 'wrap',
            'text-max-width': '70px',
            'text-valign': 'bottom',
            'text-margin-y': 4,
            width: 50,
            height: 50,
            'border-width': 2,
            'border-color': '#fff',
          },
        },
        { selector: '.status-failed', style: { 'background-color': '#ef4444' } },
        { selector: '.status-processing', style: { 'background-color': '#eab308' } },
        { selector: '.status-pending', style: { 'background-color': '#94a3b8' } },
        { selector: ':selected', style: { 'border-width': 3, 'border-color': '#1e293b' } },
      ],
      layout: {
        name: 'cose',
        padding: 40,
        nodeRepulsion: 8000,
        idealEdgeLength: 100,
        animate: true,
        animationDuration: 500,
      },
      wheelSensitivity: 0.3,
    })

    cyInstance.on('tap', 'node.doc-node', (evt) => {
      const doc = evt.target.data('doc')
      if (doc) openPanel(doc)
    })
  } catch (e) {
    console.error('Cytoscape init error', e)
  } finally {
    cyLoading.value = false
  }
}

watch(docs, () => {
  if (viewMode.value === 'node') nextTick(() => initCytoscape())
})

function fileIcon(type) {
  const map = { pdf: FileText, docx: FileText, xlsx: FileSpreadsheet, csv: FileSpreadsheet, txt: FileText, md: FileText, html: Globe }
  return map[type] || FileText
}

function fileColor(type) {
  const map = { pdf: '#ef4444', docx: '#2563eb', xlsx: '#16a34a', csv: '#16a34a', txt: '#64748b', md: '#7c3aed', html: '#ea580c' }
  return map[type] || '#94a3b8'
}

function statusLabel(s) {
  return { ready: '完成', processing: '處理中', pending: '等待', failed: '失敗', done: '完成' }[s] || s
}

function statusTagType(s) {
  return { ready: 'success', done: 'success', processing: 'warning', pending: 'info', failed: 'danger' }[s] || 'info'
}
</script>

<style scoped>
.import-result-summary {
  margin-bottom: 4px;
}

.docs-root {
  display: flex;
  height: 100%;
  overflow: hidden;
  background: #f8fafc;
  font-family: -apple-system, 'Microsoft JhengHei', sans-serif;
}

.kb-sidebar {
  width: 220px;
  min-width: 220px;
  background: #f1f5f9;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.kb-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 8px;
}
.kb-sidebar-title {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.kb-list {
  list-style: none;
  padding: 4px 8px;
  margin: 0;
  flex: 1;
  overflow-y: auto;
}
.kb-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #475569;
  transition: background 0.15s;
  position: relative;
}
.kb-item:hover { background: #e2e8f0; }
.kb-item.active { background: #dbeafe; color: #1d4ed8; font-weight: 600; }
.kb-icon { font-size: 15px; flex-shrink: 0; }
.kb-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-count {
  font-size: 11px;
  background: #e2e8f0;
  color: #64748b;
  padding: 1px 7px;
  border-radius: 10px;
}
.kb-item.active .kb-count { background: #bfdbfe; color: #1d4ed8; }
.kb-more { opacity: 0; transition: opacity 0.15s; color: #94a3b8; cursor: pointer; }
.kb-item:hover .kb-more { opacity: 1; }
.kb-sidebar-footer { padding: 12px; border-top: 1px solid #e2e8f0; display: flex; flex-direction: column; gap: 6px; }
/* lucide 圖示取代 emoji */
.kb-icon-lucide { flex-shrink: 0; color: #94a3b8; }
.kb-item.active .kb-icon-lucide { color: #1d4ed8; }
/* 拖曳高亮 */
.kb-item--drag-over {
  background: #dbeafe !important;
  box-shadow: inset 0 0 0 2px #3b82f6;
  border-radius: 7px;
}
.kb-item-wrapper { display: flex; flex-direction: column; }
.kb-expand-btn {
  display: flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; flex-shrink: 0;
  border: none; background: none; cursor: pointer; padding: 0;
  color: #94a3b8; border-radius: 3px;
}
.kb-expand-btn:hover { background: #cbd5e1; color: #475569; }
.kb-doc-list { list-style: none; margin: 0; padding: 0; }
.kb-doc-item {
  display: flex; align-items: center; gap: 5px;
  padding: 3px 8px 3px 28px;
  font-size: 12px; color: #475569; cursor: pointer;
  border-radius: 5px; margin: 1px 6px;
}
.kb-doc-item:hover { background: #dbeafe; color: #1d4ed8; }
.kb-doc-icon { flex-shrink: 0; color: #94a3b8; }
.kb-doc-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-doc-loading { padding: 3px 8px 3px 28px; font-size: 11px; color: #94a3b8; }
.kb-doc-empty { padding: 3px 8px 3px 28px; font-size: 11px; color: #cbd5e1; }

.docs-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: margin-right 0.3s ease;
  min-width: 0;
}

.docs-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 20px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  flex-wrap: wrap;
  flex-shrink: 0;
}
/* 麵包屑（主內容區頂部） */
.main-breadcrumb {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px 0;
  font-size: 13px;
  color: #94a3b8;
  flex-shrink: 0;
}
.mbc-base { color: #94a3b8; }
.mbc-sep  { color: #cbd5e1; }
.mbc-current { color: #475569; font-weight: 500; }
/* 舊 breadcrumb（已移除，保留選擇器避免殘留報錯） */
.breadcrumb { display: none; }
.bc-sep { color: #94a3b8; }
.bc-kb  { color: #2563eb; }
/* 搜尋列 */
.search-bar {
  flex: none;
  width: 480px;
  min-width: 240px;
  display: flex;
  align-items: center;
  gap: 0;
  height: 34px;
  border: 1.5px solid #e2e8f0;
  border-radius: 20px;
  background: #f8fafc;
  padding: 0 10px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.search-bar:focus-within {
  border-color: #409eff;
  box-shadow: 0 0 0 2px #409eff22;
  background: #fff;
}
.sbar-icon {
  color: #94a3b8;
  flex-shrink: 0;
  margin-right: 6px;
}
.sbar-input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 13px;
  color: #1e293b;
  min-width: 0;
}
.sbar-input::placeholder { color: #94a3b8; }
.sbar-clear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px; height: 20px;
  border: none;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  border-radius: 50%;
  flex-shrink: 0;
  padding: 0;
}
.sbar-clear:hover { background: #f1f5f9; color: #475569; }
.sbar-divider {
  width: 1px; height: 16px;
  background: #e2e8f0;
  margin: 0 8px;
  flex-shrink: 0;
}
.sbar-send {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px; height: 28px;
  border: none;
  background: transparent;
  color: #409eff;
  cursor: pointer;
  border-radius: 50%;
  flex-shrink: 0;
  padding: 0;
  transition: background 0.15s;
}
.sbar-send:hover:not(:disabled) { background: #e0f0ff; }
.sbar-send:disabled { color: #cbd5e1; cursor: not-allowed; }
.sbar-ai-toggle {
  display: flex;
  align-items: center;
  padding: 3px 10px;
  border: none;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
  background: #f1f5f9;
  color: #64748b;
  transition: background 0.15s, color 0.15s;
}
.sbar-ai-toggle--on {
  background: #409eff;
  color: #fff;
}
.sbar-ai-toggle:hover:not(.sbar-ai-toggle--on) { background: #e2e8f0; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.view-toggle { overflow: hidden; }
/* Gmail 全選控制 */
.gmail-select {
  display: flex;
  align-items: center;
  border: 1.5px solid #d1d5db;
  border-radius: 6px;
  overflow: hidden;
  height: 30px;
  background: #fff;
  transition: border-color 0.15s;
}
.gmail-select:hover { border-color: #409eff; }
.gmail-select__box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  position: relative;
  flex-shrink: 0;
}
.gmail-select__box::before {
  content: '';
  display: block;
  width: 16px;
  height: 16px;
  border: 2px solid #9ca3af;
  border-radius: 3px;
  background: #fff;
  transition: border-color 0.15s, background 0.15s;
}
.gmail-select__box:hover::before { border-color: #409eff; }
.gmail-select__box--checked::before {
  background: #409eff;
  border-color: #409eff;
}
.gmail-select__box--indeterminate::before {
  background: #409eff;
  border-color: #409eff;
}
.gmail-select__tick {
  position: absolute;
  left: 50%; top: 50%;
  transform: translate(-50%, -55%) rotate(45deg);
  width: 5px; height: 9px;
  border-right: 2px solid #fff;
  border-bottom: 2px solid #fff;
  pointer-events: none;
}
.gmail-select__dash {
  position: absolute;
  left: 50%; top: 50%;
  transform: translate(-50%, -50%);
  width: 9px; height: 2px;
  background: #fff;
  border-radius: 1px;
  pointer-events: none;
}
.gmail-select__arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 100%;
  border: none;
  border-left: 1px solid #e5e7eb;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}
.gmail-select__arrow:hover { background: #f3f4f6; color: #374151; }

.docs-content { flex: 1; overflow-y: auto; padding: 20px; }

.grid-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, 175px);
  gap: 16px;
}
.doc-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.15s, transform 0.1s, border-color 0.15s;
  position: relative;
  display: flex;
  flex-direction: column;
}
.doc-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.1);
  transform: translateY(-1px);
}
.doc-card--select-mode {
  cursor: default;
}
.doc-card:hover .card-check-wrap,
.card-check-wrap--visible {
  opacity: 1 !important;
  pointer-events: all !important;
}
.doc-card--selected {
  border-color: #409eff;
  box-shadow: 0 0 0 2px #409eff33;
}
.doc-card--trash {
  opacity: 0.75;
  cursor: default;
}
.doc-card--trash:hover {
  opacity: 1;
}
.card-thumb--deleted {
  filter: grayscale(60%);
}
/* card checkbox wrapper */
.card-check-wrap {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 10;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}
/* 圓形自製勾選按鈕 */
.card-check-btn {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 2px solid rgba(255,255,255,0.9);
  background: rgba(255,255,255,0.85);
  box-shadow: 0 1px 4px rgba(0,0,0,0.18);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}
.card-check-btn:hover {
  border-color: #409eff;
  box-shadow: 0 0 0 3px #409eff33;
}
.card-check-btn svg {
  width: 12px;
  height: 12px;
  display: block;
}
.card-check-btn--checked {
  background: #409eff;
  border-color: #409eff;
  box-shadow: 0 2px 6px rgba(64,158,255,0.45);
}
/* toolbar 全選 checkbox override */
.select-all-checkbox {
  margin-right: 6px;
}
.select-all-checkbox .el-checkbox__inner {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  border-width: 2px;
}
.select-all-checkbox .el-checkbox__inner::after {
  left: 5px;
  top: 2px;
  width: 5px;
  height: 9px;
}
/* batch ops bar */
.batch-ops {
  display: flex;
  align-items: center;
  gap: 6px;
}
.batch-count {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}
.batch-chip-count {
  font-size: 12px;
  color: #409eff;
  white-space: nowrap;
  font-weight: 600;
}
.batch-divider {
  color: #dcdfe6;
  font-size: 14px;
  margin: 0 2px;
}
.card-tag-chip--selected {
  outline: 2px solid #409eff !important;
  outline-offset: 1px;
  cursor: pointer;
}
.card-tag-chip { cursor: default; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.card-thumb {
  height: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.file-badge {
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0,0,0,0.32);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 3px;
}
.card-thumb-cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  border-radius: 4px 4px 0 0;
}
.card-body { padding: 10px 12px; flex: 1; }
.card-title {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 5px;
}
.card-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 4px;
}
.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot-ready, .dot-done { background: #22c55e; }
.dot-processing { background: #eab308; animation: blink 1.2s infinite; }
.dot-pending { background: #94a3b8; }
.dot-failed { background: #ef4444; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
.chunk-count { margin-left: auto; }
.card-kb { margin-bottom: 2px; }
.card-date { font-size: 11px; color: #94a3b8; }
.card-actions { position: absolute; top: 6px; right: 6px; }

.table-view { padding-bottom: 16px; }

.node-view {
  position: relative;
  width: 100%;
  height: calc(100vh - 200px);
}
.cy-container {
  width: 100%;
  height: 100%;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #fff;
}
.cy-legend {
  position: absolute;
  bottom: 20px;
  left: 16px;
  background: rgba(255,255,255,0.9);
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.legend-item { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #475569; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

.search-results-wrap { flex: 1; overflow-y: auto; padding: 20px; }
.search-results-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  font-size: 14px;
  color: #1e293b;
  font-weight: 600;
}
.result-count { color: #64748b; font-weight: 400; }
.search-result-list { display: flex; flex-direction: column; gap: 10px; }
.search-result-card {
  display: flex;
  gap: 14px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.search-result-card:hover { box-shadow: 0 2px 10px rgba(0,0,0,0.08); }
.src-thumb {
  width: 44px; height: 44px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.src-body { flex: 1; overflow: hidden; }
.src-title { font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 4px; }
.src-snippet {
  font-size: 12px;
  color: #64748b;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  margin-bottom: 6px;
}
.src-meta { display: flex; align-items: center; gap: 8px; }
.score-badge {
  font-size: 11px;
  color: #2563eb;
  background: #eff6ff;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.pagination-bar {
  padding: 10px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid #e2e8f0;
  background: #fff;
  flex-shrink: 0;
}
.pagination-info {
  font-size: 13px;
  color: #64748b;
}
.pagination-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-panel {
  position: fixed;
  top: var(--titlebar-h, 0px);
  right: var(--agent-panel-w, 0px);
  width: 380px;
  height: calc(100vh - var(--titlebar-h, 0px));
  background: #fff;
  border-left: 1px solid #e2e8f0;
  border-radius: 16px 0 0 16px;
  display: flex;
  flex-direction: column;
  z-index: 100;
  box-shadow: -8px 0 32px rgba(0,0,0,0.1);
  transform: translateX(100%);
  transition: transform 0.3s ease, right 0.25s ease;
}
.detail-panel.panel-visible {
  transform: translateX(0);
}
.panel-resize-handle {
  position: absolute;
  left: -3px;
  top: 0;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 110;
}
.panel-resize-handle:hover,
.panel-resize-handle:active {
  background: linear-gradient(90deg, transparent 1px, #409eff 1px, #409eff 3px, transparent 3px);
}
.panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}
.panel-thumb {
  width: 36px; height: 36px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.panel-title-wrap { flex: 1; overflow: hidden; }
.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 3px;
}
.panel-tabs { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
:deep(.panel-tabs .el-tabs__header) { padding-left: 16px; margin-bottom: 0; }
:deep(.el-tabs__content) { flex: 1; overflow: hidden; padding: 0; }
:deep(.el-tab-pane) { height: 100%; display: flex; flex-direction: column; }

.info-section { padding: 14px 16px; }
.info-row {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
  font-size: 13px;
}
.info-label { color: #64748b; width: 78px; flex-shrink: 0; }
.info-val { color: #1e293b; flex: 1; word-break: break-all; }
.panel-actions { padding: 12px 16px; }

.chunk-badge { margin-left: 6px; }
.chunks-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid #f1f5f9;
  flex-shrink: 0;
}
.chunks-scroll { flex: 1; padding: 8px 16px; }
.chunk-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.chunk-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.chunk-len { margin-left: auto; font-size: 11px; color: #94a3b8; }
.chunk-content {
  font-size: 12px;
  line-height: 1.7;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

.content-scroll { flex: 1; padding: 16px; }
.content-xlsx-hint {
  padding: 10px 16px 0;
  font-size: 12px;
  color: #2563eb;
  background: #eff6ff;
  border-bottom: 1px solid #bfdbfe;
}
.full-content {
  font-size: 12px;
  line-height: 1.8;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Courier New', monospace;
  margin: 0;
}

/* ── 試算表 tab ── */
.sheet-tab-bar { padding: 8px 12px 0; border-bottom: 1px solid #e2e8f0; }
.sheet-scroll { flex: 1; overflow: auto; width: 100%; }
.sheet-table-wrap { padding: 12px 16px; display: inline-block; min-width: 100%; box-sizing: border-box; }
.sheet-table { border-collapse: collapse; font-size: 12px; }
.sheet-table :deep(td),
.sheet-table :deep(th) {
  border: 1px solid #cbd5e1;
  padding: 4px 8px;
  white-space: nowrap;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sheet-table :deep(tr:nth-child(even) td) { background: #f8fafc; }
.sheet-table :deep(tr:first-child td),
.sheet-table :deep(th) { background: #e2e8f0; font-weight: 600; }

/* ── 編輯 tab ── */
.edit-scroll { height: 100%; }
.edit-form {
  padding: 16px 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.edit-field { display: flex; flex-direction: column; gap: 6px; }
.edit-label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}
.edit-hint {
  font-size: 11px;
  color: #94a3b8;
}
.edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
}


.color-swatches { display: flex; gap: 8px; flex-wrap: wrap; }
.swatch {
  width: 26px; height: 26px;
  border-radius: 50%;
  cursor: pointer;
  transition: transform 0.1s;
  outline-offset: 2px;
}
.kb-advanced-toggle {
  display: flex; align-items: center; gap: 10px;
  margin: 12px 0 14px;
  cursor: pointer;
  user-select: none;
}
.kb-advanced-line {
  flex: 1; height: 1px; background: var(--el-border-color-lighter);
}
.kb-advanced-label {
  font-size: 12px; color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.swatch:hover { transform: scale(1.2); }

.loading-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  gap: 10px;
  color: #94a3b8;
  font-size: 13px;
}

/* ── Tag Filter（側欄） ── */
.tag-filter {
  padding: 10px 12px 6px;
  border-top: 1px solid #f1f5f9;
}
.tag-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  max-height: 240px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 2px;
}
.tag-chips::-webkit-scrollbar { width: 4px; }
.tag-chips::-webkit-scrollbar-thumb { background: #ddd; border-radius: 2px; }
.tag-chips::-webkit-scrollbar-track { background: transparent; }
.tag-filter-title {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
  text-transform: uppercase;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.tag-filter-title-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
.tag-batch-bar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 0 8px;
}
.tag-batch-row1 {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tag-batch-row2 {
  display: flex;
  gap: 6px;
}
.tag-batch-count {
  font-size: 11px;
  color: #64748b;
}
.tag-chip--selected-manage {
  outline: 2px solid #409eff;
  outline-offset: 1px;
}
.tag-chips--manage {
  flex-direction: column;
  flex-wrap: nowrap;
  gap: 0;
}
.tag-chips--manage .tag-chip {
  width: 100%;
  height: auto;
  padding: 4px 8px;
  border-radius: 4px;
  justify-content: flex-start;
  box-sizing: border-box;
}

/* ── 待審核區塊 ── */
.pending-review-block {
  padding: 10px 12px;
  border-top: 1px solid #f1f5f9;
  background: #fffbeb;
}
.pending-review-title {
  font-size: 11px;
  color: #b45309;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.pending-review-badge {
  background: #fde68a;
  color: #92400e;
  border-radius: 8px;
  padding: 1px 7px;
  font-size: 10px;
  font-weight: 600;
}
.pending-review-actions {
  display: flex;
  gap: 6px;
}

/* ── Card Tags（grid mode） ── */
.card-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  min-height: 22px;
  margin-bottom: 2px;
}
.add-tag-btn {
  display: none;
  font-size: 11px;
  padding: 0 4px;
  height: 20px;
  color: #94a3b8;
}
.doc-card:hover .add-tag-btn { display: inline-flex; }

/* ── Tag Picker（popover 內容） ── */
.tag-picker { display: flex; flex-direction: column; gap: 4px; max-height: 200px; overflow-y: auto; }
.tag-pick-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.1s;
}
.tag-pick-item:hover { background: #f1f5f9; }
.tag-pick-empty { font-size: 12px; color: #bbb; padding: 8px; text-align: center; }
.lucide-spin {
  animation: lucide-rotate 1s linear infinite;
}
@keyframes lucide-rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ══════════════════════════════════
   概覽 Tab（overview）
══════════════════════════════════ */
.overview-scroll { height: 100%; }
.overview-body {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-bottom: 16px;
}

/* 區塊容器 */
.section-block {
  padding: 14px 16px;
  border-bottom: 1px solid #f1f5f9;
}
.section-block:last-child { border-bottom: none; }

/* 區塊標題 */
.section-title {
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 10px;
}
.section-title--toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}
.section-title--toggle:hover { color: #64748b; }

/* 欄位 */
.ov-field { margin-bottom: 8px; }
.ov-field:last-child { margin-bottom: 0; }
.ov-label {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 4px;
}

/* URL 行 */
.ov-url-row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  word-break: break-all;
}
.ov-url-link {
  font-size: 12px;
  word-break: break-all;
  line-height: 1.4;
}

/* KB 行 */
.ov-kb-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}

/* muted / error */
.ov-val-muted { font-size: 13px; color: #cbd5e1; }
.ov-val-error { font-size: 12px; color: #ef4444; word-break: break-all; }

/* 3 欄統計 */
.ov-row-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 4px;
}
.ov-stat {
  background: #f8fafc;
  border-radius: 8px;
  padding: 8px 10px;
  text-align: center;
}
.ov-stat-label {
  font-size: 10px;
  color: #94a3b8;
  margin-bottom: 4px;
}
.ov-stat-val {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}
.ov-stat-date { font-size: 11px; font-weight: 500; }

/* 完整內容展開 */
.ov-content-body {
  margin-top: 8px;
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #f1f5f9;
  border-radius: 6px;
}
.ov-content-body .full-content {
  padding: 10px 12px;
  margin: 0;
}

/* 試算表展開 */
.ov-sheet-body { margin-top: 8px; }

/* 操作按鈕區 */
.ov-actions-block {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>