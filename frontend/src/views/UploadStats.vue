<template>
  <div class="stats-page">
    <header class="page-head">
      <h1>数据统计</h1>
      <p>文档入库情况，以及各部门新建会话数量</p>
    </header>

    <h2 class="section-title">文档</h2>
    <div class="kpis">
      <article class="kpi kpi-main">
        <p class="label">现存文档</p>
        <p class="num">{{ stats.existing }}</p>
        <p class="hint">分布于 {{ stats.knowledge_bases }} 个知识库</p>
      </article>
      <article class="kpi">
        <p class="label">可检索</p>
        <p class="num">{{ stats.ready }}</p>
        <p class="hint">已向量化、可问答引用</p>
      </article>
      <article class="kpi">
        <p class="label">处理中 / 失败</p>
        <p class="num">{{ stats.processing }} / {{ stats.failed }}</p>
        <p class="hint">解析中尚未完成 · 失败需重传</p>
      </article>
      <article class="kpi">
        <p class="label">今日上传</p>
        <p class="num">{{ stats.today }}</p>
        <p class="hint">按北京时区今日 0 点起</p>
      </article>
    </div>

    <el-card class="chart-card" shadow="never">
      <template #header>
        <div class="card-head">
          <span>最近 7 天上传趋势</span>
          <span class="sub">按北京时区自然日统计</span>
        </div>
      </template>
      <div class="chart-wrap">
        <canvas ref="chartEl"></canvas>
      </div>
    </el-card>

    <h2 class="section-title">新建会话</h2>
    <div class="kpis kpis-3">
      <article class="kpi kpi-main">
        <p class="label">现存会话</p>
        <p class="num">{{ stats.conversations }}</p>
        <p class="hint">当前范围内未删除的会话总数</p>
      </article>
      <article class="kpi">
        <p class="label">今日新建</p>
        <p class="num">{{ stats.conversations_today }}</p>
        <p class="hint">按北京时区今日 0 点起</p>
      </article>
      <article class="kpi">
        <p class="label">近 7 天新建</p>
        <p class="num">{{ stats.conversations_week }}</p>
        <p class="hint">含今日，按自然日累计</p>
      </article>
    </div>

    <el-card class="chart-card" shadow="never">
      <template #header>
        <div class="card-head">
          <span>最近 7 天新建会话</span>
          <span class="sub">按北京时区自然日统计</span>
        </div>
      </template>
      <div class="chart-wrap">
        <canvas ref="convChartEl"></canvas>
      </div>
    </el-card>

    <el-card v-if="auth.isSuperAdmin && stats.by_tenant.length" class="tenant-card" shadow="never">
      <template #header>各部门存量</template>
      <el-table :data="stats.by_tenant" stripe>
        <el-table-column label="租户" min-width="160">
          <template #default="{ row }">{{ cellText(row.tenant_name || row.tenant_slug) }}</template>
        </el-table-column>
        <el-table-column label="用户名称" min-width="140">
          <template #default="{ row }">{{ cellText(row.username) }}</template>
        </el-table-column>
        <el-table-column label="现存文档" width="140">
          <template #default="{ row }">{{ cellText(row.existing) }}</template>
        </el-table-column>
        <el-table-column label="现存会话" width="140">
          <template #default="{ row }">{{ cellText(row.conversations) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from "vue";
import { Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip } from "chart.js";
import http from "../api/http";
import { useAuthStore } from "../stores/auth";
import { cellText } from "../utils/emptyCell";

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip);

const auth = useAuthStore();
const chartEl = ref<HTMLCanvasElement | null>(null);
const convChartEl = ref<HTMLCanvasElement | null>(null);
let chart: Chart | null = null;
let convChart: Chart | null = null;
const stats = reactive({
  existing: 0,
  total: 0,
  ready: 0,
  failed: 0,
  processing: 0,
  knowledge_bases: 0,
  today: 0,
  last_7_days: [] as { date: string; count: number }[],
  conversations: 0,
  conversations_today: 0,
  conversations_week: 0,
  conversations_last_7_days: [] as { date: string; count: number }[],
  by_tenant: [] as {
    tenant_name: string;
    tenant_slug: string;
    username?: string;
    existing: number;
    conversations?: number;
  }[],
});

function renderLine(
  canvas: HTMLCanvasElement | null,
  series: { date: string; count: number }[],
  color: string,
  label: string,
): Chart | null {
  if (!canvas) return null;
  return new Chart(canvas, {
    type: "line",
    data: {
      labels: series.map((d) => d.date.slice(5)),
      datasets: [
        {
          label,
          data: series.map((d) => d.count),
          borderColor: color,
          backgroundColor: color === "#3b82f6" ? "rgba(59, 130, 246, 0.12)" : "rgba(16, 185, 129, 0.12)",
          fill: true,
          tension: 0.35,
          pointRadius: 4,
          pointBackgroundColor: color,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "#64748b" },
        },
        y: {
          beginAtZero: true,
          ticks: { precision: 0, color: "#64748b" },
          grid: { color: "rgba(148, 163, 184, 0.25)" },
        },
      },
    },
  });
}

onMounted(async () => {
  const { data } = await http.get("/analytics/uploads");
  const d = data.data || {};
  stats.existing = d.existing ?? d.total ?? 0;
  stats.total = d.total || 0;
  stats.ready = d.ready || 0;
  stats.failed = d.failed || 0;
  stats.processing = d.processing || 0;
  stats.knowledge_bases = d.knowledge_bases || 0;
  stats.today = d.today || 0;
  stats.last_7_days = d.last_7_days || [];
  stats.conversations = d.conversations || 0;
  stats.conversations_today = d.conversations_today || 0;
  stats.conversations_week = d.conversations_week || 0;
  stats.conversations_last_7_days = d.conversations_last_7_days || [];
  stats.by_tenant = d.by_tenant || [];
  chart?.destroy();
  convChart?.destroy();
  chart = renderLine(chartEl.value, stats.last_7_days, "#3b82f6", "上传数");
  convChart = renderLine(convChartEl.value, stats.conversations_last_7_days, "#10b981", "新建会话");
});

onUnmounted(() => {
  chart?.destroy();
  convChart?.destroy();
  chart = null;
  convChart = null;
});
</script>

<style scoped>
.stats-page {
  max-width: 1120px;
  margin: 0 auto;
  padding: 8px 4px 32px;
}
.page-head {
  margin-bottom: 20px;
}
.page-head h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 650;
  color: #0f172a;
  letter-spacing: 0.02em;
}
.page-head p {
  margin: 0;
  color: #64748b;
  font-size: 14px;
}
.kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}
.kpis-3 {
  grid-template-columns: repeat(3, 1fr);
}
@media (max-width: 960px) {
  .kpis-3 {
    grid-template-columns: 1fr 1fr;
  }
}
.section-title {
  margin: 8px 0 12px;
  font-size: 16px;
  font-weight: 650;
  color: #0f172a;
}
.kpi {
  background: #fff;
  border: 1px solid #e8eef6;
  border-radius: 14px;
  padding: 18px 18px 16px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.kpi-main {
  background: linear-gradient(180deg, #f8fbff 0%, #ffffff 70%);
  border-color: #dbeafe;
}
.label {
  margin: 0 0 10px;
  font-size: 13px;
  color: #64748b;
}
.num {
  margin: 0;
  font-size: 34px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.03em;
  line-height: 1.1;
}
.hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.4;
}
.chart-card,
.tenant-card {
  border-radius: 14px;
  border: 1px solid #e8eef6;
  margin-bottom: 16px;
}
.chart-card :deep(.el-card__header),
.tenant-card :deep(.el-card__header) {
  border-bottom: 1px solid #eef2f7;
  padding: 14px 20px;
  color: #0f172a;
  font-weight: 600;
}
.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}
.card-head .sub {
  font-weight: 400;
  font-size: 12px;
  color: #94a3b8;
}
.chart-wrap {
  height: 280px;
}
</style>
