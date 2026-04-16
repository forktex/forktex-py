/** @type {import('@rtk-query/codegen-openapi').ConfigFile} */
module.exports = {
  schemaFile: 'http://localhost:4444/openapi.json',
  apiFile: './src/api/baseApi.ts',
  outputFile: './src/api/archApi.ts',
  exportName: 'archApi',
  hooks: true,
  tag: true,
}
