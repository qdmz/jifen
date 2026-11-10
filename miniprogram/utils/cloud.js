/**
 * 云服务客户端：整个小程序只在这里初始化一次，所有页面共用
 *
 * - 数据库 / 登录都走这一个 client，不要在别处再 new 一个
 * - wx 用诊断包装过：云请求失败时会在 vConsole 打一行 [WorkBuddy Cloud] request failed，
 *   手机上看不到数据时先看这行日志（域名没加白名单、403、超时都能直接看出来）
 */
const { createMiniProgramWorkBuddyCloud } = require('@tencent-ai/workbuddy-cloud-sdk/miniprogram');
const { createDiagnosticWx } = require('./workbuddy-cloud-diagnostics');
const cfg = require('./config');

const cloud = createMiniProgramWorkBuddyCloud({
  endpoint: cfg.cloud.endpoint,
  publishableKey: cfg.cloud.publishableKey,
  workBuddyOAuthClientId: cfg.cloud.workBuddyOAuthClientId,
  wx: createDiagnosticWx(wx)
});

module.exports = { cloud };
