<!--
  Eval fixture for evals.json id 2, with PLANTED accessibility defects. Do not copy it.
  QA report: "keyboard users get stuck in the filter drawer, and the close X says nothing in
  VoiceOver". The defects are listed in EXPECTED.md next to this file.
-->
<template>
  <div class="filters">
    <button type="button" class="filters-trigger" @click="openDrawer">Filters</button>

    <div v-if="open" class="drawer-backdrop" @click="closeDrawer"></div>
    <div v-if="open" ref="drawer" class="drawer" @keydown.tab.prevent="cycleFocus">
      <div class="drawer-header">
        <span class="drawer-title">Filters</span>
        <span class="drawer-close" @click="closeDrawer">
          <svg viewBox="0 0 16 16" width="16" height="16">
            <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" stroke-width="2" />
          </svg>
        </span>
      </div>

      <div class="drawer-body">
        <div class="group-title">Category</div>
        <label v-for="c in categories" :key="c" class="option">
          <input v-model="selected" type="checkbox" :value="c" />
          {{ c }}
        </label>

        <div class="group-title">Price</div>
        <input v-model.number="maxPrice" type="range" min="0" max="500" />
        <span class="price-value">Up to ${{ maxPrice }}</span>
      </div>

      <div class="drawer-footer">
        <button type="button" @click="clearAll">Clear all</button>
        <button type="button" class="apply" @click="apply">Show results</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue';

const emit = defineEmits(['apply']);
const open = ref(false);
const drawer = ref(null);
const categories = ['Shoes', 'Jackets', 'Bags', 'Hats'];
const selected = ref([]);
const maxPrice = ref(250);

async function openDrawer() {
  open.value = true;
  await nextTick();
}

function closeDrawer() {
  open.value = false;
}

// Keeps Tab inside the drawer. The close control is a <span>, so it is never in this list.
function cycleFocus(event) {
  const items = [...drawer.value.querySelectorAll('input, button')];
  const i = items.indexOf(document.activeElement);
  const next = event.shiftKey ? (i <= 0 ? items.length - 1 : i - 1) : (i + 1) % items.length;
  items[next].focus();
}

function clearAll() {
  selected.value = [];
  maxPrice.value = 500;
}

function apply() {
  emit('apply', { categories: selected.value, maxPrice: maxPrice.value });
  closeDrawer();
}
</script>

<style scoped>
.drawer-backdrop { position: fixed; inset: 0; background: rgb(0 0 0 / 0.4); }
.drawer { position: fixed; top: 0; right: 0; bottom: 0; width: min(360px, 100vw); background: #fff; padding: 16px; overflow-y: auto; }
.drawer-header { display: flex; justify-content: space-between; align-items: center; }
.drawer-title { font-size: 20px; font-weight: 600; }
.drawer-close { cursor: pointer; padding: 4px; }
.group-title { margin-top: 16px; font-weight: 600; }
.option { display: block; }
.drawer-footer { display: flex; gap: 8px; margin-top: 24px; }
</style>
