const path = require("node:path");

const { getDefaultConfig } = require("expo/metro-config");

const projectRoot = __dirname;
const sharedRoot = path.resolve(projectRoot, "..", "shared");

const config = getDefaultConfig(projectRoot);

// `shared/` lives outside the Expo project, so Metro has to be told to watch it and
// where to look for its dependencies.
config.watchFolders = [sharedRoot];
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(sharedRoot, "node_modules"),
];

module.exports = config;
