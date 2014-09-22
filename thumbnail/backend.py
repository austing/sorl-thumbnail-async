from sorl.thumbnail.base import ThumbnailBackend
from sorl.thumbnail import default
from sorl.thumbnail.kvstores.base import add_prefix
from sorl.thumbnail.helpers import serialize, deserialize
from sorl.thumbnail.images import ImageFile
from sorl.thumbnail.parsers import parse_geometry

class AsyncThumbnailBackend(ThumbnailBackend):
    def get_thumbnail(self, file_, geometry_string, **options):
        source = ImageFile(file_)
        for key, value in self.default_options.items():
            options.setdefault(key, value)
        name = self._get_thumbnail_filename(source, geometry_string, options)
        thumbnail = ImageFile(name, default.storage)
        cached = default.kvstore.get(thumbnail)
        if cached:
            return cached
        # We don't check if thumbnail exists as sorl-thumbnail does. It becomes
        # very costly for remote storages.
        # Furthermore, I have added following code to reduce/prevent duplicate
        # tasks in celery. It's hacky.
        
        # Finally, if there is no thumbnail, we create one.
        from .tasks import create_thumbnail
        job = create_thumbnail.delay(source.name, geometry_string, **options)
        # Sometimes thumbnail generation takes quite some time, just return
        # the original image then.
        if job:
            geometry = parse_geometry(geometry_string)
            # We can't add a source row to the kvstore without the size
            # information being looked up, so add dummy information here
            # We'll need to correct this information when we generate the thumbnail
            source.set_size(geometry)
            default.kvstore.get_or_set(source)

            # We don't want to do any file access in this thread, so we tell sorlery
            # to proceed as normal and cheekily update the name and storage after
            # the hash has been calculated.
            thumbnail.set_size(geometry)
            default.kvstore.set(thumbnail, source)

            # Now we go back and manually update the thumbnail to point at the source image
            # Hopefully someone can suggest a better way to do this ... but the sorl internals
            # don't make it easy to.
            rawvalue = default.kvstore._get_raw(add_prefix(thumbnail.key))
            rawvaluearr = deserialize(rawvalue)
            rawvaluearr['name'] = file_.name
            default.kvstore._set_raw(add_prefix(thumbnail.key), serialize(rawvaluearr))
        
        thumbnail.name = file_.name
        return thumbnail
