'use strict';
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

module.exports = class InfrastructureGuard {
  constructor(serverless) {
    // v3.40's schema predates Lambda Python 3.12. Packaging uses our explicit
    // Linux artifact, so only the schema enum needs extending; AWS gets 3.12.
    const runtimeSchema = serverless.configSchemaHandler.schema.definitions.awsLambdaRuntime;
    if (!runtimeSchema || !Array.isArray(runtimeSchema.enum)) {
      throw new Error('Unexpected pinned Serverless runtime schema.');
    }
    if (!runtimeSchema.enum.includes('python3.12')) runtimeSchema.enum.push('python3.12');
    const guard = (deploying) => {
      const templateOnly = !deploying && process.env.AF_TEMPLATE_ONLY === '1';
      const args = ['-m', 'scripts.validate_infra'];
      if (templateOnly) args.push('--template-only');
      else args.push('--check-artifact');
      if (deploying) args.push('--verify-account');
      const result = spawnSync(process.env.PYTHON || 'python', args, {
        cwd: serverless.serviceDir, env: process.env, stdio: 'inherit', shell: false,
      });
      if (result.error || result.status !== 0) throw new Error('Infrastructure prerequisites are not satisfied.');
      const artifact = path.join(serverless.serviceDir, '.artifacts', 'build-manifest.json');
      if (!fs.existsSync(artifact)) throw new Error('Run python -m scripts.package_backend first.');
      const manifest = JSON.parse(fs.readFileSync(artifact, 'utf8'));
      if (!templateOnly && (manifest.template_only || manifest.missing_handlers.length)) {
        throw new Error('Template-only artifacts cannot be packaged for deployment.');
      }
    };
    this.hooks = {
      initialize: () => {
        if (serverless.processedInput.commands[0] === 'deploy') guard(true);
      },
      'before:package:initialize': () => guard(false),
    };
  }
};
