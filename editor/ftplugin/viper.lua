-- Neovim ftplugin for Viper: start the language server for .vp buffers.
-- Requires Neovim >= 0.8 and the `viper` command on PATH (with the [lsp] extra).

-- Make sure *.vp files are recognised as Viper.
vim.filetype.add({ extension = { vp = "viper" } })

if vim.fn.executable("viper") == 1 then
  local found = vim.fs.find(
    { "pyproject.toml", ".git" },
    { upward = true, path = vim.api.nvim_buf_get_name(0) }
  )[1]
  local root = found and vim.fs.dirname(found) or vim.fn.getcwd()

  vim.lsp.start({
    name = "viper-lsp",
    cmd = { "viper", "--lsp" },
    root_dir = root,
  })
end
