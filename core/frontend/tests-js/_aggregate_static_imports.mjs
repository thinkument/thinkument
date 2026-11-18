import { existsSync, statSync } from "node:fs";
import { registerHooks } from "node:module";
import path from "node:path";
import { spawnSync } from "node:child_process";
import {
  fileURLToPath,
  pathToFileURL,
} from "node:url";


const APP_ROOT = path.resolve(
  fileURLToPath(new URL("../", import.meta.url)),
);

const SRC_ROOT = path.join(APP_ROOT, "src");


function pythonStaticSpecs() {
  const code = `
import json
from __staticfiles_mgmt import get_static_root_specs

print(json.dumps([
    {
        "path": str(spec.path.resolve()),
        "logical_prefix": spec.logical_prefix,
    }
    for spec in get_static_root_specs()
]))
`.trim();

  const candidates = [
    process.env.PYTHON,
    "python3",
    "python",
  ].filter(Boolean);

  const errors = [];

  for (const executable of [...new Set(candidates)]) {
    const result = spawnSync(
      executable,
      ["-c", code],
      {
        cwd: APP_ROOT,
        encoding: "utf8",
        env: {
          ...process.env,
          PYTHONPATH: [
            SRC_ROOT,
            process.env.PYTHONPATH,
          ]
            .filter(Boolean)
            .join(path.delimiter),
        },
      },
    );

    if (result.error) {
      errors.push(
        `${executable}: ${result.error.message}`,
      );
      continue;
    }

    if (result.status !== 0) {
      errors.push(
        `${executable}: ${String(result.stderr || "").trim()}`,
      );
      continue;
    }

    try {
      const specs = JSON.parse(
        String(result.stdout || "").trim(),
      );

      if (
        !Array.isArray(specs)
        || !specs.length
        || specs.some(
          (spec) => (
            !spec
            || typeof spec.path !== "string"
            || !spec.path
            || typeof spec.logical_prefix !== "string"
          ),
        )
      ) {
        throw new TypeError(
          "Python static registry returned no specs",
        );
      }

      return Object.freeze(
        specs.map((spec) => Object.freeze({
          root: path.resolve(spec.path),
          logicalPrefix: spec.logical_prefix,
        })),
      );
    } catch (error) {
      errors.push(
        `${executable}: invalid static-root output: ${error.message}`,
      );
    }
  }

  throw new Error(
    "could not read the Python static-root registry:\n"
    + errors.join("\n"),
  );
}


const STATIC_SPECS = pythonStaticSpecs();


function containingStaticSpec(filename) {
  const resolved = path.resolve(filename);

  for (const spec of STATIC_SPECS) {
    const relative = path.relative(
      spec.root,
      resolved,
    );

    if (
      relative === ""
      || (
        relative !== ".."
        && !relative.startsWith(`..${path.sep}`)
        && !path.isAbsolute(relative)
      )
    ) {
      return spec;
    }
  }

  return null;
}


function logicalFilenameFor(
  filename,
  spec,
) {
  const relative = path
    .relative(spec.root, filename)
    .split(path.sep)
    .join("/");

  return spec.logicalPrefix
    ? `${spec.logicalPrefix}/${relative}`
    : relative;
}


function physicalCandidateFor(
  logicalTarget,
  spec,
) {
  let relative = logicalTarget;

  if (spec.logicalPrefix) {
    if (logicalTarget === spec.logicalPrefix) {
      return null;
    }

    const prefix = `${spec.logicalPrefix}/`;
    if (!logicalTarget.startsWith(prefix)) {
      return null;
    }

    relative = logicalTarget.slice(
      prefix.length,
    );
  }

  return path.join(
    spec.root,
    ...relative.split("/"),
  );
}


function splitSpecifier(specifier) {
  const match = String(specifier).match(
    /^([^?#]*)([?#].*)?$/,
  );

  return {
    pathname: match?.[1] ?? String(specifier),
    suffix: match?.[2] ?? "",
  };
}


function resolveAggregateStaticImport(
  specifier,
  context,
  nextResolve,
) {
  if (
    !specifier.startsWith("./")
    && !specifier.startsWith("../")
  ) {
    return nextResolve(
      specifier,
      context,
    );
  }

  if (
    !context.parentURL
    || !context.parentURL.startsWith("file:")
  ) {
    return nextResolve(
      specifier,
      context,
    );
  }

  const parentFilename = fileURLToPath(
    context.parentURL,
  );

  const parentSpec = containingStaticSpec(
    parentFilename,
  );

  if (!parentSpec) {
    return nextResolve(
      specifier,
      context,
    );
  }

  const parentLogicalFilename = logicalFilenameFor(
    parentFilename,
    parentSpec,
  );

  const {
    pathname: importPath,
    suffix,
  } = splitSpecifier(specifier);

  const logicalTarget = path.posix.normalize(
    path.posix.join(
      path.posix.dirname(
        parentLogicalFilename,
      ),
      importPath,
    ),
  );

  if (
    logicalTarget === ".."
    || logicalTarget.startsWith("../")
    || path.posix.isAbsolute(logicalTarget)
  ) {
    throw new Error(
      "static import escapes the aggregate static namespace: "
      + `${specifier} from ${parentLogicalFilename}`,
    );
  }

  const matches = STATIC_SPECS
    .map(
      (spec) => physicalCandidateFor(
        logicalTarget,
        spec,
      ),
    )
    .filter(Boolean)
    .filter(
      (candidate) => (
        existsSync(candidate)
        && statSync(candidate).isFile()
      ),
    );

  if (!matches.length) {
    throw new Error(
      "aggregate static import does not exist: "
      + `${logicalTarget} `
      + `(imported from ${parentLogicalFilename})`,
    );
  }

  if (matches.length > 1) {
    throw new Error(
      "aggregate static import has multiple physical owners: "
      + `${logicalTarget}: `
      + JSON.stringify(matches),
    );
  }

  return {
    url: `${pathToFileURL(matches[0]).href}${suffix}`,
    shortCircuit: true,
  };
}


registerHooks({
  resolve: resolveAggregateStaticImport,
});


export function resolveAggregateStaticFilename(
  specifier,
  parentFilename,
) {
  if (
    !specifier.startsWith("./")
    && !specifier.startsWith("../")
  ) {
    return null;
  }

  const parentSpec = containingStaticSpec(
    parentFilename,
  );

  if (!parentSpec) {
    return null;
  }

  const {
    pathname: importPath,
  } = splitSpecifier(specifier);

  const parentLogicalFilename = logicalFilenameFor(
    parentFilename,
    parentSpec,
  );

  const logicalTarget = path.posix.normalize(
    path.posix.join(
      path.posix.dirname(
        parentLogicalFilename,
      ),
      importPath,
    ),
  );

  if (
    logicalTarget === ".."
    || logicalTarget.startsWith("../")
    || path.posix.isAbsolute(logicalTarget)
  ) {
    throw new Error(
      "static import escapes the aggregate static namespace: "
      + `${specifier} from ${parentLogicalFilename}`,
    );
  }

  const matches = STATIC_SPECS
    .map(
      (spec) => physicalCandidateFor(
        logicalTarget,
        spec,
      ),
    )
    .filter(Boolean)
    .filter(
      (candidate) => (
        existsSync(candidate)
        && statSync(candidate).isFile()
      ),
    );

  if (!matches.length) {
    throw new Error(
      "aggregate static import does not exist: "
      + `${logicalTarget} `
      + `(imported from ${parentLogicalFilename})`,
    );
  }

  if (matches.length > 1) {
    throw new Error(
      "aggregate static import has multiple physical owners: "
      + `${logicalTarget}: `
      + JSON.stringify(matches),
    );
  }

  return matches[0];
}
