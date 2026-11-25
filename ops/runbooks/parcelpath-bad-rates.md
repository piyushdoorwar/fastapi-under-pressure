# ParcelPath answers unreadable

From chapter 11.

ParcelPath returned at least one answer the API could not
read as a rate. Quotes fell back to the estimate.

Check: `parcelpath_bad_rate` log lines name the missing or
wrong field. Check ParcelPath's changelog for a release.

Act: if ParcelPath changed its format, add a model for the
new version (chapter 11). Never add a default to make it
parse.
