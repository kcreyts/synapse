import synapse.exc as s_exc

import synapse.lib.cache as s_cache
import synapse.lib.stormtypes as s_stormtypes

stormcmds = [
    {
        'name': 'model.edge.set',
        'descr': 'Set an key-value for an edge verb that exists in the current view.',
        'cmdargs': (
            ('verb', {'help': 'The edge verb to add a key to.'}),
            ('key', {'help': 'The key name (e.g. doc).'}),
            ('valu', {'help': 'The string value to set.'}),
        ),
        'storm': '''
            $verb = $cmdopts.verb
            $key = $cmdopts.key
            $lib.model.edge.set($verb, $key, $cmdopts.valu)
            $lib.print('Set edge key: verb={verb} key={key}', verb=$verb, key=$key)
        ''',
    },
    {
        'name': 'model.edge.get',
        'descr': 'Retrieve key-value pairs an edge verb in the current view.',
        'cmdargs': (
            ('verb', {'help': 'The edge verb to retrieve.'}),
        ),
        'storm': '''
            $verb = $cmdopts.verb
            $kvpairs = $lib.model.edge.get($verb)
            if $kvpairs {
                $lib.print('verb = {verb}', verb=$verb)
                for ($key, $valu) in $kvpairs {
                    $lib.print('    {key} = {valu}', key=$key, valu=$valu)
                }
            } else {
                $lib.print('verb={verb} contains no key-value pairs.', verb=$verb)
            }
        ''',
    },
    {
        'name': 'model.edge.del',
        'descr': 'Delete a global key-value pair for an edge verb in the current view.',
        'cmdargs': (
            ('verb', {'help': 'The edge verb to delete documentation for.'}),
            ('key', {'help': 'The key name (e.g. doc).'}),
        ),
        'storm': '''
            $verb = $cmdopts.verb
            $key = $cmdopts.key
            $lib.model.edge.del($verb, $key)
            $lib.print('Deleted edge key: verb={verb} key={key}', verb=$verb, key=$key)
        ''',
    },
    {
        'name': 'model.edge.list',
        'descr': 'List all edge verbs in the current view and their doc key (if set).',
        'storm': '''
            $edgelist = $lib.model.edge.list()
            if $edgelist {
                $lib.print('\nname       doc')
                $lib.print('----       ---')
                for ($verb, $kvdict) in $edgelist {
                    $verb = $verb.ljust(10)

                    $doc = $kvdict.doc
                    if ($doc=$lib.null) { $doc = '' }

                    $lib.print('{verb} {doc}', verb=$verb, doc=$doc)
                }
                $lib.print('')
            } else {
                $lib.print('No edge verbs found in the current view.')
            }
        ''',
    },
]

class LibModel(s_stormtypes.Lib):
    '''
    A collection of method around the data model
    '''
    def __init__(self, runt, name=()):
        s_stormtypes.Lib.__init__(self, runt, name)
        self.model = runt.model

    def addLibFuncs(self):
        self.locls.update({
            'type': self._methType,
            'prop': self._methProp,
            'form': self._methForm,
            'edge': ModelEdge(self.runt),
        })

    @s_cache.memoize(size=100)
    async def _methType(self, name):
        type_ = self.model.type(name)
        if type_ is not None:
            return ModelType(type_)

    @s_cache.memoize(size=100)
    async def _methProp(self, name):
        prop = self.model.prop(name)
        if prop is not None:
            return ModelProp(prop)

    @s_cache.memoize(size=100)
    async def _methForm(self, name):
        form = self.model.form(name)
        if form is not None:
            return ModelForm(form)

class ModelForm(s_stormtypes.Prim):

    def __init__(self, form, path=None):

        s_stormtypes.Prim.__init__(self, form, path=path)

        self.locls.update({
            'name': form.name,
            'prop': self._getFormProp,
        })

        self.ctors.update({
            'type': self._ctorFormType,
        })

    def _ctorFormType(self, path=None):
        return ModelType(self.valu.type, path=path)

    def _getFormProp(self, name):
        prop = self.valu.prop(name)
        if prop is not None:
            return ModelProp(prop)

class ModelProp(s_stormtypes.Prim):

    def __init__(self, prop, path=None):

        s_stormtypes.Prim.__init__(self, prop, path=path)

        self.locls.update({
            'name': prop.name,
            'full': prop.full,
        })

        self.ctors.update({
            'form': self._ctorPropForm,
            'type': self._ctorPropType,
        })

    def _ctorPropType(self, path=None):
        return ModelType(self.valu.type, path=path)

    def _ctorPropForm(self, path=None):
        return ModelForm(self.valu.form, path=path)

class ModelType(s_stormtypes.Prim):
    '''
    A Storm types wrapper around a lib.types.Type
    '''
    def __init__(self, valu, path=None):
        s_stormtypes.Prim.__init__(self, valu, path=path)
        self.locls.update({
            'name': valu.name,
            'repr': self._methRepr,
            'norm': self._methNorm,
        })

    async def _methRepr(self, valu):
        nval = self.valu.norm(valu)
        return self.valu.repr(nval[0])

    async def _methNorm(self, valu):
        return self.valu.norm(valu)

class ModelEdge(s_stormtypes.Prim):
    '''
    Inspect light edges and manipulate key-value attributes.
    '''
    # Note: The use of extprops in hive paths in this class is an artifact of the
    # original implementation which used extended property language which had a
    # very bad cognitive overload with the cortex extended properties, but we
    # dont' want to change underlying data. epiphyte 20200703

    # restrict list of keys which we allow to be set/del through this API.
    validedgekeys = (
        'doc',
    )

    def __init__(self, runt):

        s_stormtypes.Prim.__init__(self, None)

        self.runt = runt

        self.hivepath = ('cortex', 'model', 'edges')

        self.locls.update({
            'get': self._methEdgeGet,
            'set': self._methEdgeSet,
            'del': self._methEdgeDel,
            'list': self._methEdgeList,
        })

    async def _chkEdgeVerbInView(self, verb):
        async for vverb in self.runt.snap.view.getEdgeVerbs():
            if vverb == verb:
                return

        raise s_exc.NoSuchName(mesg=f'No such edge verb in the current view', name=verb)

    async def _chkKeyName(self, key):
        if key not in self.validedgekeys:
            raise s_exc.NoSuchProp(mesg=f'The requested key is not valid for light edge metadata.',
                                   name=key)

    async def _methEdgeGet(self, verb):
        verb = await s_stormtypes.tostr(verb)
        await self._chkEdgeVerbInView(verb)

        path = self.hivepath + (verb, 'extprops')
        return await self.runt.snap.core.getHiveKey(path) or {}

    async def _methEdgeSet(self, verb, key, valu):
        verb = await s_stormtypes.tostr(verb)
        await self._chkEdgeVerbInView(verb)

        key = await s_stormtypes.tostr(key)
        await self._chkKeyName(key)

        valu = await s_stormtypes.tostr(valu)

        path = self.hivepath + (verb, 'extprops')
        kvdict = await self.runt.snap.core.getHiveKey(path) or {}

        kvdict[key] = valu
        await self.runt.snap.core.setHiveKey(path, kvdict)

    async def _methEdgeDel(self, verb, key):
        verb = await s_stormtypes.tostr(verb)
        await self._chkEdgeVerbInView(verb)

        key = await s_stormtypes.tostr(key)
        await self._chkKeyName(key)

        path = self.hivepath + (verb, 'extprops')
        kvdict = await self.runt.snap.core.getHiveKey(path) or {}

        oldv = kvdict.pop(key, None)
        if oldv is None:
            raise s_exc.NoSuchProp(mesg=f'Key is not set for this edge verb',
                                   verb=verb, name=key)

        await self.runt.snap.core.setHiveKey(path, kvdict)

    async def _methEdgeList(self):
        retn = []
        async for verb in self.runt.snap.view.getEdgeVerbs():
            path = self.hivepath + (verb, 'extprops')
            kvdict = await self.runt.snap.core.getHiveKey(path) or {}
            retn.append((verb, kvdict))

        return retn
