
import unittest
from tests.utils.runtest import makesuite, run

from tests.utils.allocators import GetAllocatingTestAllocator
from tests.utils.memory import CreateTypes, OffsetPtr

from System import GC, IntPtr
from System.Runtime.InteropServices import Marshal

from Ironclad import CPyMarshal, CPython_destructor_Delegate, Python25Mapper, PythonMapper
from Ironclad.Structs import PyObject, PyListObject, PyTypeObject



class Python25Mapper_PyList_Type_Test(unittest.TestCase):

    def testPyList_Type(self):
        mapper = Python25Mapper()
        
        typeBlock = Marshal.AllocHGlobal(Marshal.SizeOf(PyTypeObject))
        try:
            mapper.SetData("PyList_Type", typeBlock)
            self.assertEquals(mapper.PyList_Type, typeBlock, "type address not stored")
            self.assertEquals(mapper.Retrieve(typeBlock), list, "type not mapped")
        finally:
            Marshal.FreeHGlobal(typeBlock)


    def testPyListTypeField_tp_dealloc(self):
        calls = []
        class MyPM(Python25Mapper):
            def PyList_Dealloc(self, listPtr):
                calls.append(listPtr)
        
        self.mapper = MyPM()
        
        typeBlock = Marshal.AllocHGlobal(Marshal.SizeOf(PyTypeObject))
        try:
            self.mapper.SetData("PyList_Type", typeBlock)
            GC.Collect() # this will make the function pointers invalid if we forgot to store references to the delegates

            deallocDgt = CPyMarshal.ReadFunctionPtrField(typeBlock, PyTypeObject, "tp_dealloc", CPython_destructor_Delegate)
            deallocDgt(IntPtr(12345))
            self.assertEquals(calls, [IntPtr(12345)], "wrong calls")
        finally:
            Marshal.FreeHGlobal(typeBlock)


    def testPyListTypeField_tp_free(self):
        calls = []
        class MyPM(Python25Mapper):
            def PyObject_Free(self, listPtr):
                calls.append(listPtr)
        
        self.mapper = MyPM()
        
        typeBlock = Marshal.AllocHGlobal(Marshal.SizeOf(PyTypeObject))
        try:
            self.mapper.SetData("PyList_Type", typeBlock)
            GC.Collect() # this will make the function pointers invalid if we forgot to store references to the delegates

            freeDgt = CPyMarshal.ReadFunctionPtrField(typeBlock, PyTypeObject, "tp_free", CPython_destructor_Delegate)
            freeDgt(IntPtr(12345))
            self.assertEquals(calls, [IntPtr(12345)], "wrong calls")
            
        finally:
            Marshal.FreeHGlobal(typeBlock)
            
        

    def testPyList_DeallocDecRefsItemsAndCallsCorrectFreeFunction(self):
        frees = []
        mapper = Python25Mapper(GetAllocatingTestAllocator([], frees))
        
        calls = []
        def CustomFree(ptr):
            calls.append(ptr)
        freeDgt = PythonMapper.PyObject_Free_Delegate(CustomFree)
        
        typeBlock = Marshal.AllocHGlobal(Marshal.SizeOf(PyTypeObject))
        try:
            mapper.SetData("PyList_Type", typeBlock)
            CPyMarshal.WriteFunctionPtrField(typeBlock, PyTypeObject, "tp_free", freeDgt)
            
            listPtr = mapper.Store([1, 2, 3])
            itemPtrs = []
            dataStore = CPyMarshal.ReadPtrField(listPtr, PyListObject, "ob_item")
            for _ in range(3):
                itemPtrs.append(CPyMarshal.ReadPtr(dataStore))
                dataStore = OffsetPtr(dataStore, CPyMarshal.PtrSize)
            
            mapper.PyList_Dealloc(listPtr)
            
            for itemPtr in itemPtrs:
                self.assertEquals(itemPtr in frees, True, "did not decref item")
                self.assertRaises(KeyError, lambda: mapper.RefCount(itemPtr))
            self.assertEquals(calls, [listPtr], "did not call type's free function")
            mapper.PyObject_Free(listPtr)
        finally:
            Marshal.FreeHGlobal(typeBlock)
        
        
    def testStoreList(self):
        mapper = Python25Mapper()
        deallocTypes = CreateTypes(mapper)
        listPtr = mapper.Store([1, 2, 3])
        try:
            typePtr = CPyMarshal.ReadPtrField(listPtr, PyObject, "ob_type")
            self.assertEquals(typePtr, mapper.PyList_Type, "wrong type")

            dataStore = CPyMarshal.ReadPtrField(listPtr, PyListObject, "ob_item")
            for i in range(1, 4):
                self.assertEquals(mapper.Retrieve(CPyMarshal.ReadPtr(dataStore)), i, "contents not stored")
                self.assertEquals(mapper.RefCount(CPyMarshal.ReadPtr(dataStore)), 1, "bad refcount for items")
                dataStore = OffsetPtr(dataStore, CPyMarshal.PtrSize)
        finally:
            mapper.DecRef(listPtr)
            deallocTypes()


class Python25Mapper_PyList_Functions_Test(unittest.TestCase):
    
    def testPyList_New_ZeroLength(self):
        allocs = []
        mapper = Python25Mapper(GetAllocatingTestAllocator(allocs, []))
        deallocTypes = CreateTypes(mapper)
        
        listPtr = mapper.PyList_New(0)
        try:
            self.assertEquals(allocs, [(listPtr, Marshal.SizeOf(PyListObject))], "bad alloc")

            listStruct = Marshal.PtrToStructure(listPtr, PyListObject)
            self.assertEquals(listStruct.ob_refcnt, 1, "bad refcount")
            self.assertEquals(listStruct.ob_type, mapper.PyList_Type, "bad type")
            self.assertEquals(listStruct.ob_size, 0, "bad ob_size")
            self.assertEquals(listStruct.ob_item, IntPtr.Zero, "bad data pointer")
            self.assertEquals(listStruct.allocated, 0, "bad allocated")
            self.assertEquals(mapper.Retrieve(listPtr), [], "mapped to wrong object")
        finally:
            mapper.DecRef(listPtr)
            deallocTypes()
    
    
    def testPyList_New_NonZeroLength(self):
        allocs = []
        mapper = Python25Mapper(GetAllocatingTestAllocator(allocs, []))
        deallocTypes = CreateTypes(mapper)
        
        SIZE = 27
        listPtr = mapper.PyList_New(SIZE)
        try:
            listStruct = Marshal.PtrToStructure(listPtr, PyListObject)
            self.assertEquals(listStruct.ob_refcnt, 1, "bad refcount")
            self.assertEquals(listStruct.ob_type, mapper.PyList_Type, "bad type")
            self.assertEquals(listStruct.ob_size, SIZE, "bad ob_size")
            self.assertEquals(listStruct.allocated, SIZE, "bad allocated")
            
            dataPtr = listStruct.ob_item
            self.assertNotEquals(dataPtr, IntPtr.Zero, "failed to allocate space for data")
            
            expectedAllocs = [(dataPtr, (SIZE * CPyMarshal.PtrSize)), (listPtr, Marshal.SizeOf(PyListObject))]
            self.assertEquals(set(allocs), set(expectedAllocs), "allocated wrong")
            
            for _ in range(SIZE):
                self.assertEquals(CPyMarshal.ReadPtr(dataPtr), IntPtr.Zero, "failed to zero memory")
                dataPtr = OffsetPtr(dataPtr, CPyMarshal.PtrSize)
            
        finally:
            mapper.DecRef(listPtr)
            deallocTypes()
    
    
    def testPyList_Append(self):
        allocs = []
        deallocs = []
        mapper = Python25Mapper(GetAllocatingTestAllocator(allocs, deallocs))
        deallocTypes = CreateTypes(mapper)
        
        listPtr = mapper.PyList_New(0)
        try:
            self.assertEquals(allocs, [(listPtr, Marshal.SizeOf(PyListObject))], "bad alloc")

            item1 = object()
            item2 = object()
            itemPtr1 = mapper.Store(item1)
            itemPtr2 = mapper.Store(item2)
            try:
                try:
                    self.assertEquals(mapper.PyList_Append(listPtr, itemPtr1), 0, "failed to report success")
                    self.assertEquals(len(allocs), 4, "didn't allocate memory for data store (list; item1; item2; data store comes 4th)")

                    dataPtrAfterFirstAppend = CPyMarshal.ReadPtrField(listPtr, PyListObject, "ob_item")
                    self.assertEquals(allocs[3], (dataPtrAfterFirstAppend, CPyMarshal.PtrSize), "allocated wrong amount of memory")
                    self.assertEquals(CPyMarshal.ReadPtr(dataPtrAfterFirstAppend), itemPtr1, "failed to fill memory")
                    self.assertEquals(mapper.RefCount(itemPtr1), 2, "failed to incref new contents")
                    self.assertEquals(mapper.Retrieve(listPtr), [item1], "retrieved wrong list")
                finally:
                    # ensure that references are not lost when reallocing data
                    mapper.DecRef(itemPtr1)

                self.assertEquals(mapper.PyList_Append(listPtr, itemPtr2), 0, "failed to report success")
                self.assertEquals(len(allocs), 5, "didn't allocate memory for new, larger data store")
                self.assertEquals(deallocs, [dataPtrAfterFirstAppend])

                dataPtrAfterSecondAppend = CPyMarshal.ReadPtrField(listPtr, PyListObject, "ob_item")
                self.assertEquals(allocs[4], (dataPtrAfterSecondAppend, (CPyMarshal.PtrSize * 2)), 
                                  "allocated wrong amount of memory")
                self.assertEquals(CPyMarshal.ReadPtr(dataPtrAfterSecondAppend), itemPtr1, 
                                  "failed to keep reference to first item")
                self.assertEquals(CPyMarshal.ReadPtr(OffsetPtr(dataPtrAfterSecondAppend, CPyMarshal.PtrSize)), itemPtr2, 
                                  "failed to keep reference to first item")
                self.assertEquals(mapper.RefCount(itemPtr1), 1, "wrong refcount for item existing only in list")
                self.assertEquals(mapper.RefCount(itemPtr2), 2, "wrong refcount newly-added item")
                self.assertEquals(mapper.Retrieve(listPtr), [item1, item2], "retrieved wrong list")
            finally:
                mapper.DecRef(itemPtr2)
        finally:
            mapper.DecRef(listPtr)
            deallocTypes()
        
        
    def testPyList_SetItem_RefCounting(self):
        mapper = Python25Mapper()
        deallocTypes = CreateTypes(mapper)
        
        listPtr = mapper.PyList_New(4)
        itemPtr1 = mapper.Store(object())
        itemPtr2 = mapper.Store(object())
        try:
            try:
                self.assertEquals(mapper.PyList_SetItem(listPtr, 0, itemPtr1), 0, "returned error code")
            except Exception, e:
                print e
                raise
            self.assertEquals(mapper.RefCount(itemPtr1), 1, "reference count wrong")
            
            mapper.IncRef(itemPtr1) # reference was stolen a couple of lines ago
            self.assertEquals(mapper.PyList_SetItem(listPtr, 0, itemPtr2), 0, "returned error code")
            self.assertEquals(mapper.RefCount(itemPtr1), 1, "failed to decref replacee")
            self.assertEquals(mapper.RefCount(itemPtr2), 1, "reference count wrong")
            
            mapper.IncRef(itemPtr2) # reference was stolen a couple of lines ago
            self.assertEquals(mapper.PyList_SetItem(listPtr, 0, IntPtr.Zero), 0, "returned error code")
            self.assertEquals(mapper.RefCount(itemPtr2), 1, "failed to decref replacee")
            
        finally:
            mapper.DecRef(itemPtr2)
            mapper.DecRef(itemPtr1)
            mapper.DecRef(listPtr)
            deallocTypes()
        
        
    def testPyList_SetItem_CompleteList(self):
        mapper = Python25Mapper()
        deallocTypes = CreateTypes(mapper)
        
        listPtr = mapper.PyList_New(4)
        item1 = object()
        item2 = object()
        itemPtr1 = mapper.Store(item1)
        itemPtr2 = mapper.Store(item2)
        mapper.IncRef(itemPtr1)
        mapper.IncRef(itemPtr2)
        try:
            mapper.PyList_SetItem(listPtr, 0, itemPtr1)
            mapper.PyList_SetItem(listPtr, 1, itemPtr2)
            mapper.PyList_SetItem(listPtr, 2, itemPtr1)
            mapper.PyList_SetItem(listPtr, 3, itemPtr2)
            
            self.assertEquals(mapper.Retrieve(listPtr), [item1, item2, item1, item2], "lists not synchronised")
            
        finally:
            mapper.DecRef(listPtr)
            deallocTypes()
    
    
    def testPyList_SetItem_Failures(self):
        mapper = Python25Mapper()
        deallocTypes = CreateTypes(mapper)
        
        objPtr = mapper.Store(object())
        listPtr = mapper.PyList_New(4)
        try:
            mapper.IncRef(objPtr) # failing PyList_SetItem will still steal a reference
            self.assertEquals(mapper.PyList_SetItem(objPtr, 1, objPtr), -1, "did not detect non-list")
            self.assertEquals(mapper.RefCount(objPtr), 1, "reference not stolen")
            
            mapper.IncRef(objPtr)
            self.assertEquals(mapper.PyList_SetItem(listPtr, 4, objPtr), -1, "did not detect set outside bounds")
            self.assertEquals(mapper.RefCount(objPtr), 1, "reference not stolen")
            
            mapper.IncRef(objPtr)
            self.assertEquals(mapper.PyList_SetItem(listPtr, -1, objPtr), -1, "did not detect set outside bounds")
            self.assertEquals(mapper.RefCount(objPtr), 1, "reference not stolen")
            
            mapper.IncRef(objPtr)
            self.assertEquals(mapper.PyList_SetItem(IntPtr.Zero, 1, objPtr), -1, "did not detect null list")
            self.assertEquals(mapper.RefCount(objPtr), 1, "reference not stolen")
        
            # list still contains uninitialised values
            self.assertRaises(ValueError, mapper.Retrieve, listPtr)
        
        finally:
            mapper.DecRef(listPtr)
            mapper.DecRef(objPtr)
            deallocTypes()
            
    
    def testPyList_SetItem_PreexistingIpyList(self):
        mapper = Python25Mapper()
        deallocTypes = CreateTypes(mapper)
        
        item = object()
        itemPtr = mapper.Store(item)
        listPtr = mapper.Store([1, 2, 3])
        try:
            self.assertEquals(mapper.PyList_SetItem(listPtr, 1, itemPtr), 0, "did not report success")
            self.assertEquals(mapper.Retrieve(listPtr), [1, item, 3], "did not replace list content")
            
        finally:
            mapper.DecRef(listPtr)
            deallocTypes()
        
    
    def testRetrieveListContainingItself(self):
        mapper = Python25Mapper()
        deallocTypes = CreateTypes(mapper)
        
        listPtr = mapper.PyList_New(1)
        try:
            mapper.PyList_SetItem(listPtr, 0, listPtr)
            self.assertEquals(mapper.RefCount(listPtr), 1, "list should be the only thing owning a reference to it")
            realList = mapper.Retrieve(listPtr)
            self.assertEquals(len(realList), 1, "wrong size list")
            anotherReferenceToRealList = realList[0]
            self.assertEquals(realList is anotherReferenceToRealList, True, "wrong list contents")
        finally:
            deallocTypes()
        
        # yes, we do leak listPtr. 
        # no, that isn't good. 
        # yes, please do submit a patch :)
        
    
    def testRetrieveListContainingItselfIndirectly(self):
        mapper = Python25Mapper()
        deallocTypes = CreateTypes(mapper)
        
        listPtr1 = mapper.PyList_New(1)
        listPtr2 = mapper.PyList_New(1)
        listPtr3 = mapper.PyList_New(1)
        try:
            mapper.PyList_SetItem(listPtr1, 0, listPtr2)
            mapper.PyList_SetItem(listPtr2, 0, listPtr3)
            mapper.PyList_SetItem(listPtr3, 0, listPtr1)
            
            realList1 = mapper.Retrieve(listPtr1)
            realList2 = mapper.Retrieve(listPtr2)
            realList3 = mapper.Retrieve(listPtr3)
            
            anotherReferenceToRealList1 = realList3[0]
            anotherReferenceToRealList2 = realList1[0]
            anotherReferenceToRealList3 = realList2[0]
            
            self.assertEquals(realList1 is anotherReferenceToRealList1, True, "wrong list contents")
            self.assertEquals(realList2 is anotherReferenceToRealList2, True, "wrong list contents")
            self.assertEquals(realList3 is anotherReferenceToRealList3, True, "wrong list contents")
        finally:
            deallocTypes()
    
        # yes, more leaks
    
    
        
    def testDeleteList(self):
        deallocs = []
        mapper = Python25Mapper(GetAllocatingTestAllocator([], deallocs))
        deallocTypes = CreateTypes(mapper)
        
        item1 = object()
        item2 = object()
        itemPtr1 = mapper.Store(item1)
        itemPtr2 = mapper.Store(item2)
        
        listPtr = mapper.PyList_New(0)
        try:
            mapper.PyList_Append(listPtr, itemPtr1)
            mapper.PyList_Append(listPtr, itemPtr2)

            mapper.DecRef(itemPtr1)
            mapper.DecRef(itemPtr2)

            self.assertEquals(len(deallocs), 1, "should have deallocated original data block only at this point")
            dataStore = CPyMarshal.ReadPtrField(listPtr, PyListObject, "ob_item")

            mapper.DecRef(listPtr)
            listDeallocs = deallocs[1:]
            self.assertEquals(len(listDeallocs), 4, "should dealloc list object; data store; both items")
            expectedDeallocs = [listPtr, dataStore, itemPtr1, itemPtr2]
            self.assertEquals(set(listDeallocs), set(expectedDeallocs), "deallocated wrong stuff")
        finally:        
            deallocTypes()
        
        
    def testPyList_GetSlice(self):
        mapper = Python25Mapper()
        deallocTypes = CreateTypes(mapper)
        
        def TestSlice(originalListPtr, start, stop):
            newListPtr = mapper.PyList_GetSlice(originalListPtr, start, stop)
            try:
                self.assertEquals(mapper.Retrieve(newListPtr), mapper.Retrieve(originalListPtr)[start:stop], "bad slice")
            finally:
                mapper.DecRef(newListPtr)
        
        listPtr = mapper.Store([0, 1, 2, 3, 4, 5, 6, 7])
        try:
            slices = (
                (3, 4), (2, -1), (-5, -4), (5, 200), (999, 1000)
            )
            for (start, stop) in slices:
                TestSlice(listPtr, start, stop)
        finally:
            deallocTypes()
        
        

suite = makesuite(
    Python25Mapper_PyList_Type_Test,
    Python25Mapper_PyList_Functions_Test,
)

if __name__ == '__main__':
    run(suite)