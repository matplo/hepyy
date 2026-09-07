class HeppyyierError(Exception):
    pass


class PackageNotInstalledError(HeppyyierError):
    pass


class BuildError(HeppyyierError):
    pass


class RecipeError(HeppyyierError):
    pass


class RecipeNotFoundError(RecipeError):
    pass
