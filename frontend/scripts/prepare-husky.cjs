'use strict';

/**
 * npm prepare 钩子：初始化 husky 并修正子目录仓库场景下的 hooksPath。
 * （husky 标准初始化要求 cwd 存在 .git；本工程位于仓库子目录时该步骤
 * 会跳过，由下方逻辑直接配置 core.hooksPath，hooks 均为自包含脚本，
 * 不依赖 husky 生成的 .husky/_ 包装器。）
 */
const { execFileSync, spawnSync } = require('node:child_process');
const path = require('node:path');

const projectRoot = path.resolve(__dirname, '..');

/** 尝试标准 husky 初始化，失败不阻断 */
function initHusky() {
  const npxBin = process.platform === 'win32' ? 'npx.cmd' : 'npx';
  const result = spawnSync(npxBin, ['--no-install', 'husky'], {
    cwd: projectRoot,
    encoding: 'utf8',
  });
  if (result.status === 0) return;
  console.warn('[husky] 标准初始化已跳过（仓库子目录场景属预期）');
}

/** 按「仓库根 → 本工程 → .husky」修正 core.hooksPath */
function fixHooksPath() {
  try {
    const toplevel = execFileSync('git', ['rev-parse', '--show-toplevel'], {
      encoding: 'utf8',
      cwd: projectRoot,
    }).trim();

    const relative = path.relative(toplevel, projectRoot);
    const hooksPath = relative ? `${relative.split(path.sep).join('/')}/.husky` : '.husky';

    execFileSync('git', ['config', 'core.hooksPath', hooksPath], { cwd: projectRoot });
    // eslint-disable-next-line no-console -- 安装期提示输出
    console.log(`[husky] core.hooksPath -> ${hooksPath}`);
  } catch {
    console.warn('[husky] 未检测到可用的 git 仓库，跳过 hooksPath 设置');
  }
}

initHusky();
fixHooksPath();
