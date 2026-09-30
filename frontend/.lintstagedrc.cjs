'use strict';

module.exports = {
  '*.vue': ['eslint --fix', 'stylelint --fix', 'prettier --write'],
  '*.{js,mjs,cjs}': ['eslint --fix', 'prettier --write'],
  '*.{scss,css}': ['stylelint --fix', 'prettier --write'],
  '*.{json,md,yml,yaml,html}': ['prettier --write'],
};
